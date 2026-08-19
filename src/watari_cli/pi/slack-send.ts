import { randomUUID } from "node:crypto";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import {
  approvalPreview,
  loadSlackBotToken,
  postSlackMessage,
} from "./slack-send.mjs";

export default function (pi: ExtensionAPI) {
  let inFlight = false;

  pi.registerTool({
    name: "watari_slack_send",
    label: "Send as Watari",
    description:
      "Post one exact human-facing message as the Watari Slack app. " +
      "The tool fails closed outside interactive Pi and always shows the sender, destination, recipient, " +
      "and complete text in a human confirmation dialog before sending.",
    promptSnippet: "Send an explicitly approved message through the Watari Slack app",
    promptGuidelines: [
      "Use watari_slack_send only after the user has seen the exact destination, Watari sender identity, recipient, and complete self-contained text and has explicitly approved that exact message.",
      "Never treat a capability question, broad request, or draft request as permission to call watari_slack_send; changed text or destination requires fresh explicit approval.",
      "Never use bash, curl, or another app or account as a substitute for watari_slack_send when sending a human-facing Slack message.",
    ],
    parameters: Type.Object({
      destination: Type.String({
        description: "Human-readable Slack destination, including channel name and whether this is a thread",
      }),
      recipient: Type.String({ description: "Human-readable recipient name(s)" }),
      channel: Type.String({ description: "Actual public/private Slack channel ID, for example C0123456789" }),
      thread_ts: Type.Optional(Type.String({
        description: "Existing Slack thread timestamp; omit only for an explicitly approved new top-level post",
      })),
      text: Type.String({
        minLength: 1,
        maxLength: 40_000,
        description: "The complete exact text already shown to and approved by the user",
      }),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      if (!ctx.hasUI || ctx.mode !== "tui") {
        throw new Error("Slack送信は、Piの対話画面で本人が明示的に承認できる場合だけ実行できます。");
      }
      if (inFlight) throw new Error("別のSlack送信確認が進行中です。");
      if (signal?.aborted) throw new Error("Slack送信を中止しました。");

      inFlight = true;
      try {
        const token = loadSlackBotToken();
        const preview = approvalPreview(params);
        const approved = await ctx.ui.confirm(
          "Slack送信の最終確認",
          preview,
        );
        if (!approved) {
          return {
            content: [{ type: "text", text: "本人がSlack送信を承認しなかったため、何も送信していません。" }],
            details: { sent: false, approved: false },
          };
        }
        if (signal?.aborted) throw new Error("Slack送信を中止しました。");

        const response = await postSlackMessage({
          token,
          channel: params.channel,
          threadTs: params.thread_ts,
          text: params.text,
          clientMsgId: randomUUID(),
        });
        const actualThread = response.message?.thread_ts || response.ts;
        return {
          content: [{
            type: "text",
            text: `WatariとしてSlackへ送信し、反映を確認しました（channel ${response.channel}, thread ${actualThread}, ts ${response.ts}）。`,
          }],
          details: {
            sent: true,
            approved: true,
            sender: "Watari (Slack app)",
            channel: response.channel,
            threadTs: actualThread,
            ts: response.ts,
          },
        };
      } finally {
        inFlight = false;
      }
    },
  });
}
