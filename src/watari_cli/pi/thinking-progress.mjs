function plainProgressLine(text) {
  const lines = String(text || "")
    .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "")
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/[\u0000-\u001f\u007f-\u009f]/g, "\n")
    .split(/\n+/)
    .map((line) => line
      .trim()
      .replace(/^#{1,6}\s+/, "")
      .replace(/^[-+*]\s+/, "")
      .replace(/[\*_`~]/g, "")
      .replace(/\s+/g, " ")
      .trim())
    .filter(Boolean);
  return lines.at(-1);
}

export function latestThinkingProgress(message) {
  const thinking = (message?.content || [])
    .filter((block) => block.type === "thinking")
    .map((block) => plainProgressLine(block.thinking))
    .filter(Boolean);
  return thinking.at(-1);
}
