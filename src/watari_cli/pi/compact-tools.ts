import {
  createBashTool,
  createBashToolDefinition,
  createEditTool,
  createEditToolDefinition,
  createReadTool,
  createReadToolDefinition,
  createWriteTool,
  createWriteToolDefinition,
  type ExtensionAPI,
} from "@earendil-works/pi-coding-agent";
import { Container } from "@earendil-works/pi-tui";

export default function (pi: ExtensionAPI) {
  const originalBash = createBashTool(process.cwd());
  const bashDefinition = createBashToolDefinition(process.cwd());
  pi.registerTool({
    ...originalBash,
    name: "bash",
    renderShell: "self",
    renderCall(args, theme, context) {
      if (!context.expanded) return new Container();
      return bashDefinition.renderCall!(args, theme, context);
    },
    renderResult(result, options, theme, context) {
      if (!options.expanded) return new Container();
      return bashDefinition.renderResult!(result, options, theme, context);
    },
  });

  const originalRead = createReadTool(process.cwd());
  const readDefinition = createReadToolDefinition(process.cwd());
  pi.registerTool({
    ...originalRead,
    name: "read",
    renderShell: "self",
    renderCall(args, theme, context) {
      if (!context.expanded) return new Container();
      return readDefinition.renderCall!(args, theme, context);
    },
    renderResult(result, options, theme, context) {
      if (!options.expanded) return new Container();
      return readDefinition.renderResult!(result, options, theme, context);
    },
  });

  const originalEdit = createEditTool(process.cwd());
  const editDefinition = createEditToolDefinition(process.cwd());
  pi.registerTool({
    ...originalEdit,
    name: "edit",
    renderShell: "self",
    renderCall(args, theme, context) {
      if (!context.expanded) return new Container();
      return editDefinition.renderCall!(args, theme, context);
    },
    renderResult(result, options, theme, context) {
      if (!options.expanded) return new Container();
      return editDefinition.renderResult!(result, options, theme, context);
    },
  });

  const originalWrite = createWriteTool(process.cwd());
  const writeDefinition = createWriteToolDefinition(process.cwd());
  pi.registerTool({
    ...originalWrite,
    name: "write",
    renderShell: "self",
    renderCall(args, theme, context) {
      if (!context.expanded) return new Container();
      return writeDefinition.renderCall!(args, theme, context);
    },
    renderResult(result, options, theme, context) {
      if (!options.expanded) return new Container();
      return writeDefinition.renderResult!(result, options, theme, context);
    },
  });

  pi.on("session_start", (_event, ctx) => {
    if (ctx.hasUI) ctx.ui.setToolsExpanded(false);
  });
}
