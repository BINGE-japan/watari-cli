import type { ExtensionAPI, ExtensionContext } from '@earendil-works/pi-coding-agent';
import { Type } from 'typebox';

export default function (pi: ExtensionAPI) {
  async function open(openBrowser: boolean, ctx?: ExtensionContext) {
    const python = process.env.WATARI_PYTHON;
    if (!python) throw new Error('watari chat から起動してください。');
    const args = ['-m', 'watari_cli', 'dashboard', '--json'];
    if (!openBrowser) args.push('--no-browser');
    if (ctx) args.push('--session-context', JSON.stringify({ version: 1, model: ctx.model?.id, provider: ctx.model?.provider, thinking: pi.getThinkingLevel(), tools: pi.getActiveTools() }));
    const result = await pi.exec(python, args, { timeout: 15000 });
    if (result.code !== 0) throw new Error('ダッシュボードを開けません。ターミナルで watari dashboard を実行して確認してください。');
    const value = JSON.parse(result.stdout);
    if (typeof value.url !== 'string' || !/^http:\/\/127\.0\.0\.1:\d+\/#[-_a-zA-Z0-9]+$/.test(value.url)) throw new Error('表示先を確認できません。');
    return value;
  }
  pi.registerCommand('dashboard', {
    description: '機能・記憶・出典・接続・同期・設定のダッシュボードを開く',
    handler: async (_args, ctx) => {
      try { const result = await open(true, ctx); ctx.ui.notify(`ダッシュボード: ${result.url}\nこのパソコン専用です。1時間使わないと終了します。`, 'info'); }
      catch (error) { ctx.ui.notify(String(error), 'error'); }
    },
  });
  pi.registerTool({
    name: 'watari_dashboard', label: 'Watari dashboard',
    description: 'Open the local read-only Watari dashboard after the user requests it. Returns a freshly verified loopback URL, never the memory contents or credentials. This URL only works on the current computer; do not share it externally.',
    parameters: Type.Object({open_browser: Type.Optional(Type.Boolean({description:'Open the local browser (default true)'}))}),
    async execute(_id, params, _signal, _onUpdate, ctx) {
      const result = await open(params.open_browser !== false, ctx);
      return {content:[{type:'text',text:`ダッシュボード: ${result.url}\nこのパソコン専用です。1時間使わないと終了します。`}],details:result};
    },
  });
}
