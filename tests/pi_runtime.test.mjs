// Actual extension factories and hooks; API/Slack/Git are synthetic and offline.
// WATARI_PI_PACKAGE points to the pinned Pi installation used by CI.
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
const pkg = process.env.WATARI_PI_PACKAGE || join(execFileSync("npm", ["root", "-g"], { encoding: "utf8" }).trim(), "@earendil-works/pi-coding-agent");
const requirePi = createRequire(join(pkg, "package.json"));
const { createJiti } = requirePi("jiti");
const jiti = createJiti(import.meta.url, { fsCache: false, moduleCache: false, alias: { typebox: requirePi.resolve("typebox") } });
const root = resolve(import.meta.dirname, "..");
const helper = (name) => import(pathToFileURL(join(root, "src/watari_cli/pi", name)));
async function extension(path, extra = {}) {
  const hooks = {}, tools = {};
  const factory = await jiti.import(join(root, path), { default: true });
  factory({ on: (key, fn) => hooks[key] = fn, registerTool: (tool) => tools[tool.name] = tool, ...extra });
  return { hooks, tools };
}

test("fast mode records successful observations and resets each turn", async () => {
  const { hooks } = await extension("src/watari_cli/pi/verification-guard.ts");
  const { setPerformanceMode } = await helper("performance.mjs");
  const { verificationState } = await helper("verification.mjs");
  setPerformanceMode("fast");
  await hooks.input({ source: "interactive", text: "設定は何ですか？" });
  await hooks.tool_execution_start({ toolCallId: "read-1", toolName: "read" });
  await hooks.tool_execution_end({ toolCallId: "read-1", toolName: "read", isError: false });
  assert.equal(verificationState().requiresObservation, true);
  assert.equal(verificationState().evidenceAccepted, true);
  await hooks.input({ source: "interactive", text: "今は何時ですか？" });
  assert.equal(verificationState().evidenceAccepted, false);
  assert.equal(verificationState().observedToolCalls.size, 0);
  setPerformanceMode("balanced");
});

test("memory budgets remain hard limits for oversized identifiers and Unicode", async () => {
  const { buildMemoryContext } = await helper("memory-context.mjs");
  for (const maxBytes of [4000, 16000]) {
    const data = buildMemoryContext({ open_threads: [{ topic: "長".repeat(20000), note: "x" }] }, {}, "長", { maxBytes });
    assert.ok(Buffer.byteLength(JSON.stringify(data)) <= maxBytes);
  }
});

test("progress, final text and shutdown never auto-publish unvalidated edits", async () => {
  const commands = [];
  let dirty = false;
  const { hooks } = await extension(".pi/extensions/commit-worktree/index.ts", {
    exec: async (_command, args) => {
      commands.push(args);
      if (args[0] === "status") return { code: 0, stdout: dirty ? " M example.txt\n" : "" };
      if (args[0] === "rev-parse" && args.includes("HEAD")) return { code: 0, stdout: "baseline\n" };
      if (args[0] === "rev-parse") return { code: 0, stdout: "origin/main\n" };
      if (args[0] === "rev-list") return { code: 0, stdout: "0 0\n" };
      return { code: 0, stdout: "" };
    },
  });
  const ctx = { hasUI: false, isIdle: () => false };
  await hooks.input({ source: "interactive", text: "Fix it" }, ctx);
  dirty = true;
  await hooks.message_end({ message: { role: "assistant", content: [{ type: "text", text: "これからテストを実行します。" }] } }, ctx);
  await hooks.session_shutdown({}, ctx);
  assert.equal(commands.some(args => ["add", "commit", "push"].includes(args[0])), false);
});

test("Slack sender must match pinned identity, even for another bot named Watari", async () => {
  const slack = await helper("slack-send.mjs");
  const credentials = { token: "xoxb-synthetic", identity: { team_id: "T1", bot_id: "B1", user_id: "U1", name: "watari" } };
  let calls = 0;
  await assert.rejects(() => slack.verifySlackSender(credentials, async () => {
    calls++;
    return { json: async () => ({ ok: true, team_id: "T1", bot_id: "B2", user_id: "U2", user: "watari" }) };
  }));
  assert.equal(calls, 1);
});

test("Slack legacy credentials without pinned identity cannot send", async () => {
  const slack = await helper("slack-send.mjs");
  let calls = 0;
  await assert.rejects(() => slack.verifySlackSender({ token: "xoxb-synthetic" }, async () => { calls++; }));
  assert.equal(calls, 0);
});

test("Slack permits URL normalization but never a changed destination or prose", async () => {
  const { postSlackMessage } = await helper("slack-send.mjs");
  const params = { token: "xoxb-synthetic", channel: "C1", text: "https://example.invalid/" };
  const reply = (channel, text) => async () => ({ json: async () => ({ ok: true, channel, ts: "1.0", message: { text } }) });
  await postSlackMessage(params, reply("C1", "<https://example.invalid/>"));
  await assert.rejects(() => postSlackMessage(params, reply("C2", params.text)));
  await assert.rejects(() => postSlackMessage(params, reply("C1", "changed")));
});

test("unknown memory versions cannot be injected into a prompt", async () => {
  const { buildMemoryContext } = await helper("memory-context.mjs");
  assert.throws(() => buildMemoryContext({ schema_version: 999 }, {}, "question"));
  assert.throws(() => buildMemoryContext({}, { schema_version: 999 }, "question", { full: true }));
});

test("Slack token and identity are loaded from one config snapshot", async () => {
  const { loadSlackCredentials } = await helper("slack-send.mjs");
  let reads = 0;
  const credentials = loadSlackCredentials({}, "/synthetic", () => {
    reads++;
    return JSON.stringify({ connectors_auth: { slack: { bot_token: `xoxb-${reads}`, identity: { bot_id: `B${reads}` } } } });
  });
  assert.equal(reads, 1);
  assert.equal(credentials.token, "xoxb-1");
  assert.equal(credentials.identity.bot_id, "B1");
});

test("Slack tool refuses noninteractive use and never posts after cancellation", async () => {
  const { mkdtempSync, mkdirSync, writeFileSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const directory = mkdtempSync(join(tmpdir(), "watari-slack-test-"));
  const previousHome = process.env.XDG_CONFIG_HOME;
  const previousFetch = globalThis.fetch;
  let posts = 0, previews = [];
  try {
    mkdirSync(join(directory, "watari"));
    writeFileSync(join(directory, "watari/config.json"), JSON.stringify({ connectors_auth: { slack: {
      bot_token: "xoxb-fake", identity: { team_id:"T1", bot_id:"B1", user_id:"U1", name:"watari" },
    } } }));
    process.env.XDG_CONFIG_HOME = directory;
    globalThis.fetch = async (url) => {
      if (url.endsWith("chat.postMessage")) posts++;
      return { json: async () => ({ ok:true, team_id:"T1", bot_id:"B1", user_id:"U1", user:"watari" }) };
    };
    const { tools } = await extension("src/watari_cli/pi/slack-send.ts");
    const tool = tools.watari_slack_send;
    const params = { destination:"#synthetic", recipient:"Synthetic Recipient", channel:"C1", text:"complete\ntext" };
    await assert.rejects(() => tool.execute("test", params, undefined, undefined, { hasUI:false, mode:"print" }));
    const result = await tool.execute("test", params, undefined, undefined, {
      hasUI:true, mode:"tui", ui:{ confirm: async (_title, text) => { previews.push(text); return false; } },
    });
    assert.equal(result.details.sent, false);
    assert.equal(posts, 0);
    assert.match(previews[0], /B1/);
    assert.match(previews[0], /complete\ntext/);
  } finally {
    globalThis.fetch = previousFetch;
    if (previousHome === undefined) delete process.env.XDG_CONFIG_HOME;
    else process.env.XDG_CONFIG_HOME = previousHome;
    rmSync(directory, { recursive:true, force:true });
  }
});
