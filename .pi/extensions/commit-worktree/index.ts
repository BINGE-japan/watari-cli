import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
  COMMIT_RULE,
  ensureCommittedWorktree,
  readGitStatus,
} from "./guard.mjs";

type TurnState = {
  baselineStatus: string;
  prompt: string;
  finalized: boolean;
};

type GuardResult = {
  status: "not-git" | "clean" | "preexisting-dirty" | "failed" | "committed";
  detail?: string;
  message?: string;
};

function appendFailure(message: any, result: GuardResult) {
  const warning = result.status === "preexisting-dirty"
    ? "\n\nコミットされていない変更が作業開始時から残っているため、完了扱いにしていません。"
    : `\n\n自動コミットに失敗したため、完了扱いにしていません: ${result.detail || "原因不明"}`;
  let appended = false;
  const content = message.content.map((block: any) => {
    if (appended || block.type !== "text") return block;
    appended = true;
    return { ...block, text: `${block.text}${warning}` };
  });
  return appended ? { ...message, content } : message;
}

export default function (pi: ExtensionAPI) {
  let turn: TurnState | undefined;
  const exec = (command: string, args: string[]) => pi.exec(command, args);

  pi.on("input", async (event) => {
    if (event.source === "extension") return;
    const baseline = await readGitStatus(exec);
    turn = {
      baselineStatus: baseline.status,
      prompt: event.text,
      finalized: false,
    };
  });

  pi.on("before_agent_start", (event) => ({
    systemPrompt: `${event.systemPrompt}\n\n${COMMIT_RULE}`,
  }));

  async function finalize(ctx: ExtensionContext): Promise<GuardResult> {
    if (!turn) return { status: "clean" };
    const result = await ensureCommittedWorktree(exec, turn.baselineStatus, turn.prompt) as GuardResult;
    turn.finalized = result.status === "not-git" || result.status === "clean" || result.status === "committed";
    if (result.status === "committed" && ctx.hasUI) {
      ctx.ui.notify(`Piのコミット漏れを自動修復しました: ${result.message}`, "warning");
    } else if ((result.status === "failed" || result.status === "preexisting-dirty") && ctx.hasUI) {
      ctx.ui.notify("未コミットの変更が残っているため、作業は未完了です。", "error");
    }
    return result;
  }

  // Run before the final answer is persisted or displayed. Normally the model
  // has already made a semantic commit; this is a deterministic fallback.
  pi.on("message_end", async (event, ctx) => {
    if (event.message.role !== "assistant") return;
    if (event.message.content.some((block: any) => block.type === "toolCall")) return;
    const result = await finalize(ctx);
    if (result.status !== "failed" && result.status !== "preexisting-dirty") return;
    return { message: appendFailure(event.message, result) };
  });

  // Also cover /quit, session replacement, and an aborted turn that reaches a
  // graceful shutdown before producing a final assistant message.
  pi.on("session_shutdown", async (_event, ctx) => {
    if (!turn || turn.finalized) return;
    await finalize(ctx);
  });
}
