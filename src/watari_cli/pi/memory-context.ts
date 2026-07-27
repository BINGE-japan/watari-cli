import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { loadMemoryContext } from "./memory-context.mjs";

const MEMORY_GUIDANCE = `
【入力前に自動確認した記憶】
次のJSONは、今回のユーザー入力に対してローカルで自動検索した記憶です。
- profile: 常に反映する人物像・好み
- attention: 今すぐ効く進行中事項（最大3件）
- matches: 今回の入力に関連する詳しい記憶（最大6件）
- catalog: 記憶にある話題名の一覧。題名だけなので、matchesに無い話題の詳細を推測しない
- catalog_truncated: 一覧が上限のため省略されたか
回答はprofileとmatchesを最初から反映してください。catalogに関係しそうな題名があるのにmatchesに詳細が無く、
回答がその詳細に依存する場合だけ、記憶フォルダの該当記録を追加確認してください。
`;

export default function (pi: ExtensionAPI) {
  pi.on("before_agent_start", async (event) => {
    let payload: unknown;
    try {
      payload = await loadMemoryContext(process.env.WATARI_HOME, event.prompt);
    } catch (error) {
      payload = {
        memory_checked: false,
        error: error instanceof Error ? error.message : String(error),
      };
    }
    return {
      systemPrompt: `${event.systemPrompt}\n\n${MEMORY_GUIDANCE}${JSON.stringify(payload)}`,
    };
  });
}
