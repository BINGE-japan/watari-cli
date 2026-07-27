const MODE_KEY = Symbol.for("watari.performance-mode");

export const PERFORMANCE_MODES = Object.freeze({
  fast: Object.freeze({
    id: "fast",
    label: "爆速",
    status: "⚡ 爆速",
    description: "記憶を4KBに絞り、確認処理の余分な1往復を省略",
    thinkingLevel: "off",
  }),
  balanced: Object.freeze({
    id: "balanced",
    label: "標準",
    status: "⚖ 標準",
    description: "関連する記憶を16KB以内で確認（既定）",
    thinkingLevel: undefined,
  }),
  butler: Object.freeze({
    id: "butler",
    label: "スーパー執事",
    status: "♟ スーパー執事",
    description: "現在の記憶全体を理解し、思考を深くして回答",
    thinkingLevel: "high",
  }),
});

export function normalizePerformanceMode(value) {
  const mode = String(value || "").trim().toLowerCase();
  return Object.hasOwn(PERFORMANCE_MODES, mode) ? mode : "balanced";
}

export function getPerformanceMode() {
  if (!globalThis[MODE_KEY]) {
    globalThis[MODE_KEY] = normalizePerformanceMode(process.env.WATARI_PERFORMANCE_MODE);
  }
  return globalThis[MODE_KEY];
}

export function setPerformanceMode(value) {
  const mode = normalizePerformanceMode(value);
  globalThis[MODE_KEY] = mode;
  return mode;
}

export function performanceMemoryOptions(value = getPerformanceMode()) {
  const mode = normalizePerformanceMode(value);
  if (mode === "fast") {
    return { maxBytes: 4_000, maxMatches: 3, attentionLimit: 1, includeCatalog: false };
  }
  if (mode === "butler") return { full: true };
  return { maxBytes: 16_000, maxMatches: 6, attentionLimit: 3, includeCatalog: true };
}

export function automaticallyAcceptEvidence(value = getPerformanceMode()) {
  return normalizePerformanceMode(value) === "fast";
}

export function performanceInfo(value = getPerformanceMode()) {
  return PERFORMANCE_MODES[normalizePerformanceMode(value)];
}
