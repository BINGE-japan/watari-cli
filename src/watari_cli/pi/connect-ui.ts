import type { ExtensionAPI } from '@earendil-works/pi-coding-agent';

// Setup uses interactive MCP management, not a model prompt.
// The adapter retains the user-configured server startup lifecycles.
export default function (pi: ExtensionAPI) {
  pi.on('session_start', (_event, ctx) => {
    if (!ctx.hasUI) { ctx.shutdown(); return; }
    const command = process.env.WATARI_CONNECT_COMMAND || '/mcp setup';
    if (!/^\/mcp(?: setup| reconnect [a-zA-Z0-9_.-]{1,128})?$/.test(command)) {
      ctx.ui.notify('接続画面の指定が不正です。', 'error'); ctx.shutdown(); return;
    }
    ctx.ui.setEditorText(command);
    ctx.ui.notify('Enterで接続画面を開きます。認証が必要な接続は画面で選択してください。', 'info');
  });
  // Slash commands run before input hooks. Handle ordinary input here: throwing
  // from before_agent_start only reports an error and does NOT cancel a Pi turn.
  pi.on('input', (_event, ctx) => {
    try { if (ctx.hasUI) ctx.ui.notify('接続専用画面です。/mcp を使用してください。', 'info'); }
    catch { /* A broken notification must not turn input into a model request. */ }
    return { action: 'handled' };
  });
  pi.on('cache_warming_decision', () => ({ action: 'stop' }));
}
