import { readFileSync, realpathSync } from "node:fs";
import { dirname, join, parse } from "node:path";
import { pathToFileURL } from "node:url";

function stripTerminalControls(text) {
  return String(text)
    .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "")
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "");
}

export function compactToolLines(lines, expanded) {
  if (expanded) return lines;
  const action = lines.find((line) => stripTerminalControls(line).trim());
  return action ? [action] : [];
}

function findPiRoot(entry) {
  if (!entry) return undefined;

  let dir;
  try {
    dir = dirname(realpathSync(entry));
  } catch {
    return undefined;
  }

  const filesystemRoot = parse(dir).root;
  while (dir !== filesystemRoot) {
    try {
      const pkg = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
      if (pkg.name === "@earendil-works/pi-coding-agent") return dir;
    } catch {
      // Keep walking: most parent directories are not package roots.
    }
    dir = dirname(dir);
  }
  return undefined;
}

// NODE_OPTIONS also reaches npm and Node commands launched by tools. Only patch
// the process whose entry point belongs to Pi itself.
const piRoot = findPiRoot(process.argv[1]);
if (piRoot) {
  const settingsUrl = pathToFileURL(join(piRoot, "dist/core/settings-manager.js"));
  const toolUiUrl = pathToFileURL(
    join(piRoot, "dist/modes/interactive/components/tool-execution.js"),
  );
  const assistantUiUrl = pathToFileURL(
    join(piRoot, "dist/modes/interactive/components/assistant-message.js"),
  );
  const { SettingsManager } = await import(settingsUrl);
  const { ToolExecutionComponent } = await import(toolUiUrl);
  const { AssistantMessageComponent } = await import(assistantUiUrl);
  const { guardAssistantMessage } = await import(new URL("./politeness.mjs", import.meta.url));
  const { guardVerifiedAssistantMessage } = await import(
    new URL("./verification.mjs", import.meta.url)
  );

  // Keep reasoning and effort intact while replacing streamed reasoning text
  // with Pi's static "Thinking..." label.
  SettingsManager.prototype.getHideThinkingBlock = () => true;

  // Keep one action line per tool by default. Pi's Ctrl+O expansion still
  // reveals the complete native call/result component when details are needed.
  const renderToolExecution = ToolExecutionComponent.prototype.render;
  ToolExecutionComponent.prototype.render = function (width) {
    const lines = renderToolExecution.call(this, width);
    return compactToolLines(lines, this.expanded);
  };

  // Buffer assistant prose until the message is final. This prevents a casual
  // partial token from appearing before the deterministic message_end guard can
  // rewrite or reject it. Intermediate prose attached to tool calls stays hidden.
  const updateAssistantContent = AssistantMessageComponent.prototype.updateContent;
  AssistantMessageComponent.prototype.updateContent = function (message) {
    const hasToolCalls = message.content.some((block) => block.type === "toolCall");
    const isFinalAnswer = Boolean(message.stopReason) && !hasToolCalls;
    const displayMessage = isFinalAnswer
      ? guardVerifiedAssistantMessage(guardAssistantMessage(message))
      : {
          ...message,
          content: message.content.map((block) =>
            block.type === "text" ? { ...block, text: "" } : block,
          ),
        };
    return updateAssistantContent.call(this, displayMessage);
  };
}
