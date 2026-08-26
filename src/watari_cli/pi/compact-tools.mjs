function stripTerminalControls(text) {
  return String(text || "")
    .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "")
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/[\u0000-\u0009\u000b-\u001f\u007f-\u009f]/g, " ");
}

export function singleLine(value, maxLength = 100) {
  const line = stripTerminalControls(value).replace(/\s+/g, " ").trim();
  if (line.length <= maxLength) return line;
  return `${line.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}

export function summarizeCommand(command) {
  const raw = stripTerminalControls(command);
  const lines = raw.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const first = singleLine(lines[0] || "command");
  return lines.length > 1 ? `${first} …` : first;
}
