// Actual extension factories and hooks; API/Slack/Git are synthetic and offline.
// WATARI_PI_PACKAGE points to the pinned Pi installation used by CI.
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
const pkg = process.env.WATARI_PI_PACKAGE || join(execFileSync("npm", ["root", "-g"], { encoding: "utf8" }).trim(), "@earendil-works/pi-coding-agent");
const requirePi = createRequire(join(pkg, "package.json"));
const { createJiti } = requirePi("jiti");
const piAiEntry = requirePi.resolve.paths("@earendil-works/pi-ai").map(base => join(base, "@earendil-works/pi-ai/dist/index.js")).find(existsSync);
assert.ok(piAiEntry, "Pi AI dependency must be installed with Pi");
const jiti = createJiti(import.meta.url, { fsCache: false, moduleCache: false, alias: { typebox: requirePi.resolve("typebox"), "@earendil-works/pi-ai": piAiEntry } });
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

test("memory hook identifies WSL as the current Windows computer", async () => {
  const { mkdtempSync, mkdirSync, writeFileSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const directory = mkdtempSync(join(tmpdir(), "watari-runtime-context-"));
  const previousHome = process.env.WATARI_HOME;
  const previousDistro = process.env.WSL_DISTRO_NAME;
  const previousPlatform = Object.getOwnPropertyDescriptor(process, "platform");
  try {
    mkdirSync(join(directory, "life"));
    mkdirSync(join(directory, "learning"));
    writeFileSync(join(directory, "life/state.json"), JSON.stringify({ profile:{}, facts:{}, interests:{}, open_threads:[] }));
    writeFileSync(join(directory, "learning/state.json"), JSON.stringify({ domains:{} }));
    process.env.WATARI_HOME = directory;
    process.env.WSL_DISTRO_NAME = "Ubuntu";
    // WSL requires Linux as well as its environment markers. Simulate both on
    // every CI host rather than treating a Mac with WSL_DISTRO_NAME as Windows.
    Object.defineProperty(process, "platform", { value: "linux" });
    const { hooks } = await extension("src/watari_cli/pi/memory-context.ts");
    const result = await hooks.before_agent_start({ prompt:"ローカルURL", systemPrompt:"base" });
    assert.match(result.systemPrompt, /"runtime_context":\{/);
    assert.match(result.systemPrompt, /"computer":"windows"/);
    assert.match(result.systemPrompt, /"runtime":"wsl"/);
    assert.match(result.systemPrompt, /127\.0\.0\.1/);
  } finally {
    if (previousHome === undefined) delete process.env.WATARI_HOME;
    else process.env.WATARI_HOME = previousHome;
    if (previousDistro === undefined) delete process.env.WSL_DISTRO_NAME;
    else process.env.WSL_DISTRO_NAME = previousDistro;
    Object.defineProperty(process, "platform", previousPlatform);
    rmSync(directory, { recursive:true, force:true });
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

test("memory search reuses ranking and returns origin without unrelated context", async () => {
  const { searchMemory } = await helper("memory-context.mjs");
  const result = searchMemory({ profile:{tone:"Polite"}, facts:{ renderer:{ note:"Aurora rendering", origin:{computer:"mac"} } } }, {}, "Aurora", 5);
  assert.equal(result.matches[0].topic, "renderer");
  assert.equal(result.matches[0].origin.computer, "mac");
  assert.equal(result.profile, undefined);
  assert.throws(() => searchMemory({schema_version:999}, {}, "Aurora"));
  assert.throws(() => searchMemory({}, {}, "", 0));
});

test("memory tools reject invented or expired batch identifiers before execution", async () => {
  const { tools } = await extension("src/watari_cli/pi/memory-tools.ts");
  assert.ok(tools.watari_memory_search);
  assert.ok(tools.watari_memory_get);
  assert.ok(tools.watari_memory_prepare);
  await assert.rejects(() => tools.watari_memory_save.execute("test", {
    batch_id:"invented", decisions_json:"[]",
  }, undefined, undefined, {sessionManager:{getSessionId:()=>"synthetic"}}), /取得し直/);
});

test("memory native tools save actual session evidence offline and reject changed replay", async () => {
  const { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const dir = mkdtempSync(join(tmpdir(), "watari-memory-native-"));
  const keys = ["WATARI_HOME", "WATARI_PYTHON", "XDG_CONFIG_HOME", "XDG_STATE_HOME"];
  const previous = Object.fromEntries(keys.map(k => [k, process.env[k]]));
  try {
    for (const genre of ["life", "learning"]) {
      mkdirSync(join(dir, genre));
      writeFileSync(join(dir, genre, "log.jsonl"), "");
    }
    process.env.WATARI_HOME = dir;
    process.env.WATARI_PYTHON = process.env.WATARI_TEST_PYTHON || join(root, ".venv/bin/python");
    process.env.XDG_CONFIG_HOME = join(dir, "config");
    process.env.XDG_STATE_HOME = join(dir, "xdg-state");
    const { tools, hooks } = await extension("src/watari_cli/pi/memory-tools.ts");
    const ctx = { cwd: "/workspace/example", sessionManager: {
      getSessionId: () => "sample-session",
      getBranch: () => [{type:"message", id:"abcd1234", timestamp:"2026-01-02T00:00:00Z",
        message:{role:"user", content:"I prefer short answers."}}],
    }};
    const prepare = await tools.watari_memory_prepare.execute("p", {scope:"current"}, undefined, undefined, ctx);
    const batch = JSON.parse(prepare.content[0].text);
    assert.equal(batch.messages[0].uuid, "pi:sample-session:abcd1234");
    const args = { batch_id:batch.batch_id, decisions_json:JSON.stringify([{uuid:batch.messages[0].uuid, rows:[{
      kind:"fact", summary:"The user prefers short answers.", note:"Short answers.",
      profile:{key:"response_style", value:"Short answers.", mode:"always"},
    }]}]) };
    const saved = await tools.watari_memory_save.execute("s", args, undefined, undefined, ctx);
    assert.equal(JSON.parse(saved.content[0].text).checked, true);
    await tools.watari_memory_save.execute("s2", args, undefined, undefined, ctx);
    assert.equal(readFileSync(join(dir, "life/log.jsonl"), "utf8").trim().split("\n").length, 1);
    await assert.rejects(() => tools.watari_memory_save.execute("bad", {...args, decisions_json:"[]"}, undefined, undefined, ctx), /変更できません/);
    const found = await tools.watari_memory_search.execute("q", {query:"response_style"});
    assert.equal(JSON.parse(found.content[0].text).matches[0].topic, "response_style");
    const details = await tools.watari_memory_get.execute("g", {kind:"fact", topic:"response_style"});
    assert.equal(JSON.parse(details.content[0].text).rows[0].refs.uuid, batch.messages[0].uuid);
    await hooks.session_tree();
    await assert.rejects(() => tools.watari_memory_save.execute("old", args, undefined, undefined, ctx), /取得し直/);
  } finally {
    for (const k of keys) if (previous[k] === undefined) delete process.env[k]; else process.env[k] = previous[k];
    rmSync(dir, {recursive:true, force:true});
  }
});

test("explicit search rejects a pending save or a missing summary instead of reporting no matches", async () => {
  const { mkdtempSync, mkdirSync, writeFileSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { loadMemorySearch } = await helper("memory-context.mjs");
  const dir = mkdtempSync(join(tmpdir(), "watari-search-failure-"));
  try {
    await assert.rejects(() => loadMemorySearch(dir, "example"));
    mkdirSync(join(dir, "life")); mkdirSync(join(dir, "learning"));
    writeFileSync(join(dir, "life/state.json"), JSON.stringify({profile:{}, facts:{}}));
    writeFileSync(join(dir, "learning/state.json"), JSON.stringify({domains:{}}));
    writeFileSync(join(dir, ".watari-pending.json"), "{}");
    await assert.rejects(() => loadMemorySearch(dir, "example"), /保存処理/);
  } finally { rmSync(dir, {recursive:true, force:true}); }
});

test("memory subprocess cancellation and timeout report unknown save status", async () => {
  const { runMemoryOperation } = await helper("memory-tools.mjs");
  const { mkdtempSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const dir = mkdtempSync(join(tmpdir(), "watari-memory-cancel-"));
  try {
    const env = {...process.env, WATARI_HOME:dir, XDG_STATE_HOME:join(dir,"state"),
      XDG_CONFIG_HOME:join(dir,"config"), WATARI_PYTHON:process.env.WATARI_TEST_PYTHON || join(root,".venv/bin/python")};
    const controller = new AbortController(); controller.abort();
    assert.throws(() => runMemoryOperation({action:"get",kind:"fact",topic:"Example"}, {env,signal:controller.signal}));
    await assert.rejects(() => runMemoryOperation({action:"get",kind:"fact",topic:"Example"}, {env,timeout:1}), /制限時間/);
    assert.throws(() => runMemoryOperation({action:"get"}, {env:{WATARI_PYTHON:"relative",WATARI_HOME:dir}}), /未設定/);
  } finally { rmSync(dir, {recursive:true, force:true}); }
});

test('dashboard command and tool launch fixed Python command without reading memory into the model', async () => {
  const previous = process.env.WATARI_PYTHON;
  process.env.WATARI_PYTHON = '/synthetic/python';
  try {
    const commands = {}, calls = [];
    const { tools } = await extension('src/watari_cli/pi/dashboard.ts', {
      registerCommand: (name, def) => commands[name] = def,
      getThinkingLevel: () => "high", getActiveTools: () => ["read", "mcp"],
      exec: async (...args) => {calls.push(args);return {code:0,stdout:JSON.stringify({url:'http://127.0.0.1:4567/#synthetic-token',browser_opened:false})};},
    });
    const result = await tools.watari_dashboard.execute('id', {open_browser:false});
    assert.deepEqual(calls[0][1], ['-m','watari_cli','dashboard','--json','--no-browser']);
    assert.equal(calls[0][0], '/synthetic/python');
    assert.match(result.content[0].text,/このパソコン専用/);
    assert.ok(commands.dashboard);
    const messages=[];
    await commands.dashboard.handler('',{ui:{notify:message=>messages.push(message)}});
    assert.match(messages[0], /127\.0\.0\.1/);
  } finally {
    if(previous===undefined)delete process.env.WATARI_PYTHON;else process.env.WATARI_PYTHON=previous;
  }
});

test('connect setup only primes management command and refuses model turns', async () => {
  const previous = process.env.WATARI_CONNECT_COMMAND;
  process.env.WATARI_CONNECT_COMMAND = '/mcp setup';
  try {
    const {hooks}=await extension('src/watari_cli/pi/connect-ui.ts');
    const editor=[];
    await hooks.session_start({}, {hasUI:true,ui:{setEditorText:t=>editor.push(t),notify:()=>{}}});
    assert.deepEqual(editor,['/mcp setup']);
    assert.deepEqual(await hooks.input({text:'Call an external service'}, {hasUI:true,ui:{notify:()=>{}}}), {action:'handled'});
    assert.deepEqual(hooks.cache_warming_decision(), {action:'stop'});
    let stopped=false;
    await hooks.session_start({}, {hasUI:false,shutdown:()=>stopped=true});
    assert.equal(stopped,true);
  } finally {
    if(previous===undefined)delete process.env.WATARI_CONNECT_COMMAND;else process.env.WATARI_CONNECT_COMMAND=previous;
  }
});
