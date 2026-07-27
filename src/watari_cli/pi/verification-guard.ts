import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import {
  guardVerifiedAssistantMessage,
  requiresObservation,
  verificationState,
} from "./verification.mjs";
import { automaticallyAcceptEvidence } from "./performance.mjs";

const toolStarts = new Map<string, { name: string; args: unknown }>();

export default function (pi: ExtensionAPI) {
  pi.on("input", (event) => {
    if (event.source === "extension") return;
    const state = verificationState();
    state.requiresObservation = requiresObservation(event.text);
    state.evidenceAccepted = false;
    state.observedToolCalls = new Set();
    state.observedTools = new Map();
    toolStarts.clear();
  });

  pi.on("before_agent_start", (event) => {
    if (!verificationState().requiresObservation) return;
    const evidenceInstruction = automaticallyAcceptEvidence()
      ? "成功したツール確認は自動登録されるため、watari_evidence は呼ばないでください。"
      : "確認後、最終回答の前に watari_evidence を呼び、観測したツール名と確認内容を登録してください。";
    return {
      systemPrompt:
        event.systemPrompt +
        "\n\n【観測優先】今回の入力は質問です。実ファイル・実画面・計算・接続サービスなど、" +
        "質問に対応する情報源を利用できる場合はツールで確認してください。" +
        evidenceInstruction +
        "確認できない部分が残る場合も、確認済みの事実と推測を分け、推測であることを明示して回答を続けてください。",
    };
  });

  pi.on("tool_execution_start", (event) => {
    toolStarts.set(event.toolCallId, { name: event.toolName, args: event.args });
  });

  pi.on("tool_execution_end", (event) => {
    if (event.isError || event.toolName === "watari_evidence") return;
    const started = toolStarts.get(event.toolCallId);
    if (!started) return;
    const state = verificationState();
    state.observedToolCalls.add(event.toolCallId);
    if (automaticallyAcceptEvidence()) state.evidenceAccepted = true;
    const ids = state.observedTools.get(event.toolName) ?? [];
    state.observedTools.set(event.toolName, [...ids, event.toolCallId]);
  });

  pi.registerTool({
    name: "watari_evidence",
    label: "Confirm observations",
    description:
      "Register the successful tool observations that support the answer. " +
      "Call this only after directly checking the relevant source; it does not fetch data itself.",
    parameters: Type.Object({
      sources: Type.Array(Type.String(), {
        minItems: 1,
        description: "Names of successful tools used to observe the answer",
      }),
      summary: Type.String({ description: "What the cited observations established" }),
    }),
    async execute(_id, params) {
      const state = verificationState();
      const missing = params.sources.filter(
        (name: string) => !(state.observedTools.get(name)?.length),
      );
      if (missing.length > 0) {
        throw new Error(`Tools were not successfully observed this turn: ${missing.join(", ")}`);
      }
      const toolCallIds = params.sources.flatMap(
        (name: string) => state.observedTools.get(name) ?? [],
      );
      state.evidenceAccepted = true;
      return {
        content: [{ type: "text", text: "Observation evidence accepted." }],
        details: { sources: params.sources, toolCallIds, summary: params.summary },
      };
    },
  });

  pi.on("message_end", (event) => {
    if (event.message.role !== "assistant") return;
    if (event.message.content.some((block) => block.type === "toolCall")) return;
    const guarded = guardVerifiedAssistantMessage(event.message);
    if (guarded === event.message) return;
    return { message: guarded };
  });
}
