import { Text } from "@earendil-works/pi-tui";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

type Signal = {
  id: string;
  urgency: number;
  title: string;
  reason: string;
  source: string;
  pointer?: string | null;
};

type BriefResult = {
  signals: Signal[];
  errors: Array<{ source: string; error: string }>;
};

function format(signals: Signal[]): string {
  const lines = signals.slice(0, 3).map((signal) => {
    const mark = signal.urgency >= 3 ? "!" : signal.urgency === 2 ? "•" : "·";
    return `${mark} ${signal.title} — ${signal.reason}`;
  });
  return `確認事項\n${lines.join("\n")}`;
}

export default function (pi: ExtensionAPI) {
  let timer: ReturnType<typeof setInterval> | undefined;

  pi.registerMessageRenderer("watari-briefing", (message, _options, theme) =>
    new Text(theme.fg("accent", message.content), 1, 0),
  );

  async function refresh(ctx: ExtensionContext, markShown: boolean, notifyEmpty = false) {
    const args = ["brief", "--json"];
    if (markShown) args.push("--mark-shown");
    const result = await pi.exec("watari", args, { timeout: 120_000 });
    if (result.code !== 0) {
      if (notifyEmpty) ctx.ui.notify("確認事項を取得できませんでした。", "warning");
      return;
    }
    let parsed: BriefResult;
    try {
      parsed = JSON.parse(result.stdout) as BriefResult;
    } catch {
      if (notifyEmpty) ctx.ui.notify("確認事項を読み取れませんでした。", "warning");
      return;
    }
    if (parsed.signals.length === 0) {
      if (notifyEmpty) ctx.ui.notify("今すぐ伝える確認事項はありません。", "info");
      return;
    }
    pi.sendMessage({
      customType: "watari-briefing",
      content: format(parsed.signals),
      display: true,
      details: { signals: parsed.signals },
    }, { triggerTurn: false });
  }

  pi.on("session_start", (_event, ctx) => {
    if (ctx.mode !== "tui") return;
    void refresh(ctx, true);
    timer = setInterval(() => void refresh(ctx, true), 15 * 60 * 1000);
  });

  pi.on("session_shutdown", () => {
    if (timer) clearInterval(timer);
    timer = undefined;
  });

  pi.registerCommand("brief", {
    description: "期限・予定・未返信・未読を今の状態から確認",
    handler: async (_args, ctx) => {
      await refresh(ctx, false, true);
    },
  });
}
