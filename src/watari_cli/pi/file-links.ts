import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { linkMentionedLocalFiles, toolFileCandidate } from "./file-links.mjs";

const FILE_LINK_GUIDANCE =
  "ローカルファイルの場所を利用者へ案内するときだけ、実在するファイルの絶対パスをバッククォートで囲んで本文に書く。毎回答へファイル一覧を付けず、file://等のリンクを手作業で作らない。";

export default function (pi: ExtensionAPI) {
  const observedFiles = new Set<string>();

  pi.on("before_agent_start", (event) => ({
    systemPrompt: `${event.systemPrompt}\n\n${FILE_LINK_GUIDANCE}`,
  }));

  pi.on("tool_result", (event, ctx) => {
    if (event.isError) return;
    const candidate = toolFileCandidate(event.toolName, event.input, ctx.cwd);
    if (candidate) observedFiles.add(candidate.path);
  });

  pi.on("message_end", (event, ctx) => {
    if (event.message.role !== "assistant") return;
    if (event.message.content.some((block) => block.type === "toolCall")) return;

    let changed = false;
    const content = event.message.content.map((block) => {
      if (block.type !== "text") return block;
      const linked = linkMentionedLocalFiles(
        block.text,
        [...observedFiles],
        ctx.cwd,
        process.env.WATARI_FILE_LINK_KEY_PATH,
      );
      if (linked === block.text) return block;
      changed = true;
      return { ...block, text: linked };
    });
    if (!changed) return;
    return { message: { ...event.message, content } };
  });

  pi.on("agent_settled", () => {
    observedFiles.clear();
  });
}
