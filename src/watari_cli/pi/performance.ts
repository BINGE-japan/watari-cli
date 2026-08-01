import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
  getPerformanceMode,
  normalizePerformanceMode,
  PERFORMANCE_MODES,
  performanceInfo,
  setPerformanceMode,
} from "./performance.mjs";

const CHOICES = ["fast", "balanced", "butler"] as const;
const ALIASES: Record<string, string> = {
  fast: "fast",
  "爆速": "fast",
  balanced: "balanced",
  "標準": "balanced",
  butler: "butler",
  "スーパー執事": "butler",
};

export default function (pi: ExtensionAPI) {
  let originalThinkingLevel: ReturnType<typeof pi.getThinkingLevel> | undefined;

  function applyMode(mode: string, ctx: ExtensionContext) {
    const info = performanceInfo(mode);
    if (info.thinkingLevel) {
      pi.setThinkingLevel(info.thinkingLevel);
    } else if (originalThinkingLevel) {
      pi.setThinkingLevel(originalThinkingLevel);
    }
    if (ctx.hasUI) ctx.ui.setStatus("watari-performance", info.status);
  }

  pi.on("session_start", (_event, ctx) => {
    originalThinkingLevel ??= pi.getThinkingLevel();
    applyMode(getPerformanceMode(), ctx);
  });

  pi.on("model_select", (_event, ctx) => {
    if (getPerformanceMode() === "balanced") {
      originalThinkingLevel = pi.getThinkingLevel();
      return;
    }
    applyMode(getPerformanceMode(), ctx);
  });

  pi.registerCommand("performance", {
    description: "返信速度と記憶の詳しさを選ぶ",
    handler: async (args, ctx) => {
      const requested = ALIASES[args.trim().toLowerCase()];
      let mode = requested;
      if (!mode) {
        if (!ctx.hasUI) return;
        const selected = await ctx.ui.select(
          `現在: ${performanceInfo().label}。性能モードを選んでください`,
          CHOICES.map((id) => {
            const info = PERFORMANCE_MODES[id];
            return `${info.label} — ${info.description}`;
          }),
        );
        if (!selected) return;
        mode = CHOICES.find((id) => selected.startsWith(PERFORMANCE_MODES[id].label));
      }
      mode = normalizePerformanceMode(mode);
      setPerformanceMode(mode);
      applyMode(mode, ctx);

      const saved = await pi.exec("watari", ["performance", "--set", mode]);
      if (saved.code !== 0) {
        ctx.ui.notify("この会話では切り替えましたが、次回用の保存に失敗しました。", "warning");
        return;
      }
      ctx.ui.notify(`性能モード: ${performanceInfo(mode).label}`, "info");
    },
  });
}
