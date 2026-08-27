import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { latestThinkingProgress } from "./thinking-progress.mjs";

export default function (pi: ExtensionAPI) {
  let currentProgress: string | undefined;

  pi.registerMarkdownTransformer((markdown, { messageType }) => {
    if (messageType === "assistant-thinking") return "";
    return markdown;
  });

  pi.on("session_start", (_event, ctx) => {
    if (ctx.hasUI) ctx.ui.setHiddenThinkingLabel("");
  });

  pi.on("agent_start", (_event, ctx) => {
    currentProgress = undefined;
    if (ctx.hasUI) ctx.ui.setWorkingMessage();
  });

  pi.on("message_update", (event, ctx) => {
    if (!ctx.hasUI || event.message.role !== "assistant") return;
    const progress = latestThinkingProgress(event.message);
    if (!progress || progress === currentProgress) return;
    currentProgress = progress;
    ctx.ui.setWorkingMessage(progress);
  });

  pi.on("agent_end", (_event, ctx) => {
    currentProgress = undefined;
    if (ctx.hasUI) ctx.ui.setWorkingMessage();
  });
}
