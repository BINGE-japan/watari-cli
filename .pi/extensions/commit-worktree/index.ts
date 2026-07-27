import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
  COMMIT_RULE,
  ensurePublishedWorktree,
  readGitHead,
  readGitStatus,
} from "./guard.mjs";

type TurnState = {
  baselineStatus: string;
  baselineHead: string;
  prompt: string;
  finalized: boolean;
};

type GuardResult = {
  status: "not-git" | "clean" | "published" | "pushed" | "committed-and-pushed" |
    "preexisting-dirty" | "no-upstream" | "diverged" | "not-synchronized" | "failed";
  detail?: string;
  message?: string;
};

function appendFailure(message: any, result: GuardResult) {
  const warning = result.status === "preexisting-dirty"
    ? "\n\nコミットされていない変更が作業開始時から残っているため、完了扱いにしていません。"
    : `\n\nコミットとpushの完了条件を満たしていないため、完了扱いにしていません: ${result.detail || "原因不明"}`;
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
    const baselineHead = baseline.inRepo ? await readGitHead(exec) : "";
    turn = {
      baselineStatus: baseline.status,
      baselineHead,
      prompt: event.text,
      finalized: false,
    };
  });

  pi.on("before_agent_start", (event) => ({
    systemPrompt: `${event.systemPrompt}\n\n${COMMIT_RULE}`,
  }));

  async function finalize(ctx: ExtensionContext): Promise<GuardResult> {
    if (!turn) return { status: "clean" };
    const result = await ensurePublishedWorktree(
      exec, turn.baselineStatus, turn.baselineHead, turn.prompt,
    ) as GuardResult;
    const success = ["not-git", "clean", "published", "pushed", "committed-and-pushed"]
      .includes(result.status);
    turn.finalized = success;
    if (result.status === "committed-and-pushed" && ctx.hasUI) {
      ctx.ui.notify(`Piのコミット・push漏れを自動修復しました: ${result.message}`, "warning");
    } else if (result.status === "pushed" && ctx.hasUI) {
      ctx.ui.notify("Piのpush漏れを自動修復しました。", "warning");
    } else if (!success && ctx.hasUI) {
      ctx.ui.notify("コミットとpushが完了していないため、作業は未完了です。", "error");
    }
    return result;
  }

  // Run before the final answer is persisted or displayed. Normally the model
  // has already made a semantic commit; this is a deterministic fallback.
  pi.on("message_end", async (event, ctx) => {
    if (event.message.role !== "assistant") return;
    if (event.message.content.some((block: any) => block.type === "toolCall")) return;
    const result = await finalize(ctx);
    if (["not-git", "clean", "published", "pushed", "committed-and-pushed"].includes(result.status)) return;
    return { message: appendFailure(event.message, result) };
  });

  // Also cover /quit, session replacement, and an aborted turn that reaches a
  // graceful shutdown before producing a final assistant message.
  pi.on("session_shutdown", async (_event, ctx) => {
    if (!turn || turn.finalized) return;
    await finalize(ctx);
  });
}
