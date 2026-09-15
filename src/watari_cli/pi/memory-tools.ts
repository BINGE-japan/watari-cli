import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { StringEnum } from "@earendil-works/pi-ai";
import { loadMemorySearch } from "./memory-context.mjs";
import { runMemoryOperation } from "./memory-tools.mjs";
import { detectRuntimeContext } from "./runtime-context.mjs";

const workflow = fileURLToPath(new URL("../skill/MEMORY.md", import.meta.url));
const schema = fileURLToPath(new URL("../skill/SCHEMA.md", import.meta.url));
const text = (data: unknown) => ({ content: [{ type: "text" as const, text: JSON.stringify(data) }], details: {} });

export default function (pi: ExtensionAPI) {
  const batches = new Map<string, { batch: any; session: string; home: string; created: number; busy: boolean; payload?: string; result?: any }>();
  const clear = () => batches.clear();
  pi.on("session_shutdown", clear);
  pi.on("session_start", clear);
  pi.on("session_tree", clear);
  pi.on("before_agent_start", async event => ({
    systemPrompt: `${event.systemPrompt}\n記憶の保存・整理時だけ読む同梱資料: ${workflow}\n記憶の行形式が必要なときだけ: ${schema}`,
  }));

  pi.registerTool({
    name: "watari_memory_search", label: "Search memory",
    description: "Search relevant personal memories when the automatic context lacks detail. Returns at most 20 entries / 32KB; does not check external live state.",
    parameters: Type.Object({ query: Type.String({ minLength: 1, maxLength: 2048 }), limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 20 })) }),
    async execute(_id, params, signal) {
      signal?.throwIfAborted();
      return text(await loadMemorySearch(process.env.WATARI_HOME, params.query, params.limit));
    },
  });
  pi.registerTool({
    name: "watari_memory_get", label: "Read memory evidence",
    description: "Read exact-topic memory history, including closed topics and original references. Default 5 rows, max 20 / 32KB; use next_offset for more.",
    parameters: Type.Object({ kind: StringEnum(["fact", "thread", "interest", "study"]),
      topic: Type.String({ minLength: 1, maxLength: 2048 }), domain: Type.Optional(Type.String()),
      offset: Type.Optional(Type.Integer({ minimum: 0 })), limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 20 })) }),
    async execute(_id, params, signal) {
      return text(await runMemoryOperation({ ...params, action: "get" }, { signal }));
    },
  });
  pi.registerTool({
    name: "watari_memory_prepare", label: "Prepare memory selection",
    description: "Read MEMORY.md first. Prepare current user input or a bounded conversation batch (40 messages, equal-time group intact, 32KB). Does not save or advance read positions; service reads remain separate.",
    parameters: Type.Object({ scope: StringEnum(["current", "conversations"]) }),
    async execute(_id, params, signal, _update, ctx) {
      let request: any = { action: "prepare" };
      if (params.scope === "current") {
        const entry = [...ctx.sessionManager.getBranch()].reverse().find(e => e.type === "message" && e.message.role === "user");
        if (!entry || entry.type !== "message") throw new Error("本人の発話を取得できません。");
        const runtime = detectRuntimeContext();
        request = { action: "current", message: {
          uuid: `pi:${ctx.sessionManager.getSessionId()}:${entry.id}`, ts: entry.timestamp,
          session: ctx.sessionManager.getSessionId(), cwd: ctx.cwd, role: "user",
          text: entry.message.content, machine: runtime.machine_id, computer: runtime.computer, runtime: runtime.runtime,
        } };
      } else if (params.scope !== "conversations") throw new Error("未対応の対象です。");
      const batch = await runMemoryOperation(request, { signal });
      const now = Date.now();
      for (const [id, item] of batches) if (!item.busy && now - item.created > 30 * 60_000) batches.delete(id);
      if (batches.size >= 8) {
        const completed = [...batches].find(([, item]) => !item.busy && item.result?.checked);
        if (completed) batches.delete(completed[0]);
        else throw new Error("未完了の記憶処理が多すぎます。既存の処理を先に確認してください。");
      }
      const batch_id = randomUUID();
      batches.set(batch_id, { batch, session: ctx.sessionManager.getSessionId(), home: process.env.WATARI_HOME!, created: now, busy: false });
      return text({ batch_id, ...batch });
    },
  });
  pi.registerTool({
    name: "watari_memory_save", label: "Save selected memories",
    description: "Save a prepared batch through validated ingestion and verification. decisions_json is [{uuid,rows:[{kind,summary,note,...}]}], one decision per user UUID (empty rows skips). Do not supply ts/source/refs. Read MEMORY.md for judgment rules.",
    parameters: Type.Object({ batch_id: Type.String(), decisions_json: Type.String({ maxLength: 180_000 }), allow_new_domain: Type.Optional(Type.Boolean()) }),
    async execute(_id, params, signal, _update, ctx) {
      const item = batches.get(params.batch_id);
      if (!item || item.session !== ctx.sessionManager.getSessionId() || item.home !== process.env.WATARI_HOME || Date.now() - item.created > 30 * 60_000) {
        throw new Error("処理IDが無効です。材料を取得し直してください。");
      }
      const decisions = JSON.parse(params.decisions_json);
      const payload = JSON.stringify({ decisions, allow_new_domain: params.allow_new_domain ?? false });
      if (item.payload && item.payload !== payload) throw new Error("同じ処理IDで内容は変更できません。保存結果を確認し、必要なら材料を取得し直してください。");
      if (item.busy) throw new Error("この記憶処理は実行中です。");
      signal?.throwIfAborted();
      if (item.result) {
        if (!item.result.checked) throw new Error(`保存済みですが検査が未完了です。再保存せず確認してください: ${JSON.stringify(item.result)}`);
        return text(item.result);
      }
      item.busy = true;
      item.payload = payload;
      try {
        const result: any = await runMemoryOperation({ action: "save", batch: item.batch, decisions, allow_new_domain: params.allow_new_domain ?? false }, { signal });
        item.result = result;
        if (!result.checked) throw new Error(`保存済みですが検査が未完了です。再保存せず確認してください: ${JSON.stringify(result)}`);
        return text(result);
      } finally { item.busy = false; }
    },
  });
}
