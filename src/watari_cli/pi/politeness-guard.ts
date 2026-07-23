import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { guardAssistantMessage } from "./politeness.mjs";

/** Persist only output that satisfies Watari's non-negotiable polite-language rule. */
export default function (pi: ExtensionAPI) {
  pi.on("message_end", (event) => {
    if (event.message.role !== "assistant") return;
    const guarded = guardAssistantMessage(event.message);
    if (guarded === event.message) return;
    return { message: guarded };
  });
}
