// Watari's interactive management bridge. No MCP/auth implementation or tool calls.
// dist management APIs are private: refuse unreviewed adapter versions in main().
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createInterface } from 'node:readline/promises';
import { Writable } from 'node:stream';

export function connectionBinding(config, name, cwd, metadata) {
  const definition = config.mcpServers[name];
  return createHash('sha256').update(JSON.stringify([
    definition, metadata.computeServerHash(definition), cwd,
    config.settings?.oauthDir, config.settings?.oauthCredentialStore,
  ])).digest('hex');
}

// Public provider constraints, not personal configuration. GitHub documents that
// OAuth hosts must register an app; the adapter's preset alone is insufficient:
// https://github.com/github/github-mcp-server/blob/main/docs/host-integration.md
export function authHints(definition) {
  try {
    const url = new URL(definition.url);
    if (url.protocol === 'https:' && url.hostname === 'api.githubcopilot.com'
        && (url.pathname === '/mcp' || url.pathname.startsWith('/mcp/'))) {
      return {
        oauth_setup_required: !definition.oauth?.clientId,
        token_help_url: 'https://github.com/settings/personal-access-tokens/new',
      };
    }
  } catch {}
  return {};
}

export function definitionFingerprint(definition) {
  return createHash('sha256').update(JSON.stringify(Object.keys(definition).sort().map(key => [key, definition[key]]))).digest('hex');
}

export function classifyFailure(error, signal) {
  if (signal?.aborted) return 'cancelled';
  const errors = [];
  const visit = (err, depth = 0) => {
    if (!err || depth > 3 || errors.includes(err)) return;
    errors.push(err); visit(err.cause, depth + 1);
    if (Array.isArray(err.errors)) for (const item of err.errors.slice(0, 10)) visit(item, depth + 1);
  };
  visit(error);
  if (errors.some(e => ['OAUTH_CREDENTIAL_STORE_UNAVAILABLE','BEARER_CREDENTIAL_STORE_UNAVAILABLE'].includes(e.code))) return 'credential-store-unavailable';
  // Match SDK-owned text, never echo exception messages or response bodies.
  if (errors.some(e => e.message === 'Incompatible auth server: does not support dynamic client registration')) return 'oauth-client-required';
  if (errors.some(e => e.status === 401 || e.name === 'UnauthorizedError')) return 'needs-auth';
  if (errors.some(e => e.status === 403)) return 'forbidden';
  if (errors.some(e => e.status === 429 || (e.status >= 500 && e.status <= 599))) return 'server-error';
  if (errors.some(e => ['ETIMEDOUT','UND_ERR_CONNECT_TIMEOUT','UND_ERR_HEADERS_TIMEOUT'].includes(e.code))) return 'timeout';
  if (errors.some(e => ['ENOTFOUND','EAI_AGAIN','ECONNREFUSED','ECONNRESET','ENETUNREACH','EHOSTUNREACH'].includes(e.code))) return 'network-error';
  return 'error';
}

// readline owns raw-mode restoration; output is discarded so callback codes and
// bearer tokens never echo. Adapter validates OAuth state, issuer and token exchange.
export async function hiddenInput(signal, prompt) {
  if (!process.stdin.isTTY) throw new Error('TTY_REQUIRED');
  const sink = new Writable({write(_chunk, _encoding, done) { done(); }});
  const rl = createInterface({input: process.stdin, output: sink, terminal: true, historySize: 0});
  process.stderr.write(prompt);
  try {
    return await Promise.race([
      rl.question('', {signal}),
      new Promise(resolve => rl.once('close', () => resolve(undefined))),
      new Promise(resolve => rl.once('SIGINT', () => resolve(undefined))),
    ]);
  } finally { rl.close(); sink.destroy(); process.stderr.write('\n'); }
}

class ManagementFailure extends Error {
  constructor(status) { super(status); this.status = status; }
}

export async function manageConnection(request, deps) {
  const {name, action, cwd, binding, signal} = request;
  const {config, metadata, Manager, flow, auth, utils, bearer} = deps;
  const result = status => ({version: 1, status});
  if (!['check','auth'].includes(action) || typeof binding !== 'string' || !/^[a-f0-9]{64}$/.test(binding)) return result('invalid');
  const definition = config.mcpServers[name];
  if (!definition) return result('missing');
  if (definition.disabled === true || definition.enabled === false) return result('disabled');
  if (connectionBinding(config, name, cwd, metadata) !== binding) return result('changed');
  if (signal?.aborted) return result('cancelled');
  let manager, runtime;
  let answer = result('error');
  try {
    const storage = auth.getAuthStorageOptions(config.settings?.oauthDir, cwd, config.settings?.oauthCredentialStore);
    runtime = flow.createOAuthRuntime(signal);
    manager = new Manager(cwd);
    manager.setAuthStorageOptions(storage);
    manager.setOAuthRuntime(runtime);
    manager.setRuntimeSignal(signal);
    manager.setDefaultRequestTimeoutMs(15000);
    manager.setTraceConfig(undefined);
    // No sampling/elicitation configuration: remote services cannot request a model
    // or additional human-facing actions through this management-only client.
    if (action === 'auth') {
      const url = utils.resolveServerUrl(definition);
      if (!url) throw new ManagementFailure('unsupported-auth');
      if (definition.auth === 'bearer') {
        if (!definition.bearerTokenStore || definition.bearerToken !== undefined || definition.bearerTokenEnv !== undefined || definition.bearerTokenCommand !== undefined) throw new ManagementFailure('advanced-auth');
        const token = await deps.readSecret(signal);
        if (!token) throw new ManagementFailure('cancelled');
        if (token.length > 16384 || /[\r\n\x00-\x1f\x7f]/.test(token)) throw new ManagementFailure('invalid');
        bearer.saveBearerTokenForUrl(name, token, url);
      } else {
        if (!flow.supportsOAuth(definition)) throw new ManagementFailure('unsupported-auth');
        const state = await flow.authenticate(name, url, definition, {
          runtime, signal, authStorageOptions: storage,
          onAuthorizationUrl: deps.onAuthorizationUrl,
          openAuthorizationUrl: deps.openAuthorizationUrl,
          onAuthorizationInput: deps.onAuthorizationInput,
        });
        if (state !== 'authenticated') throw new ManagementFailure('needs-auth');
      }
    }
    const connection = await manager.connect(name, definition, signal);
    answer = connection.status === 'connected'
      ? {...result('connected'), tool_count: connection.tools.length}
      : result('needs-auth');
  } catch (error) {
    // Never print an adapter/remote exception: messages can contain URL credentials,
    // command arguments, response bodies and tokens. Expose allowlisted categories.
    answer = result(error instanceof ManagementFailure ? error.status : classifyFailure(error, signal));
  } finally {
    try { await manager?.closeAll(); } catch { answer = result('cleanup-failed'); }
    try { if (runtime) await flow.shutdownOAuth(runtime); } catch { answer = result('cleanup-failed'); }
  }
  return answer;
}

export async function main(argv) {
  const [root, action, name, binding, cwd] = argv;
  const emit = event => process.stdout.write(JSON.stringify(event) + '\n');
  // Silence adapter logs, including configuration diagnostics; warnings while
  // loading configuration reject the entire operation rather than partial config.
  for (const method of ['log','warn','error','info','debug']) console[method] = () => {};
  if (argv.length !== 5 || !['check','auth'].includes(action)) return emit({version:1,status:'invalid'});
  if (action === 'auth' && !process.stdin.isTTY) return emit({version:1,status:'tty-required'});
  const controller = new AbortController();
  const stop = () => controller.abort();
  process.once('SIGINT', stop); process.once('SIGTERM', stop);
  const deadline = action === 'auth' ? 180000 : 30000;
  const timer = setTimeout(stop, deadline);
  const hardStop = setTimeout(() => process.exit(124), deadline + 5000);
  try {
    if (JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')).version !== '2.37.0') return emit({version:1,status:'unsupported-version'});
    const load = file => import(pathToFileURL(join(root, 'dist', file)).href);
    const [configModule, metadata, manager, flow, auth, utils, bearer] = await Promise.all([
      'config.js','metadata-cache.js','server-manager.js','mcp-auth-flow.js','mcp-auth.js','utils.js','mcp-bearer-store.js',
    ].map(load));
    let warned = false;
    console.warn = () => { warned = true; };
    const config = configModule.loadMcpConfig(undefined, cwd);
    console.warn = () => {};
    if (warned) return emit({version:1,status:'config-error'});
    const require = createRequire(join(root, 'package.json'));
    const safeAuthorizationUrl = value => {
      const url = new URL(value);
      if (url.protocol !== 'https:' || url.username || url.password || value.length > 12000 || /[\x00-\x20\x7f-\x9f]/.test(value)) throw new Error('Invalid authorization URL');
      return url.href;
    };
    const answer = await manageConnection({name,action,binding,cwd,signal:controller.signal}, {
      config, metadata, Manager:manager.McpServerManager, flow, auth, utils, bearer,
      readSecret: signal => { emit({event:'input',kind:'token'}); return hiddenInput(signal, ''); },
      onAuthorizationInput: async (_url, signal) => {
        emit({event:'input',kind:'callback'});
        const value = await hiddenInput(signal, '');
        if (!signal.aborted && !value) controller.abort();
        return value;
      },
      onAuthorizationUrl: url => emit({event:'authorization',url:safeAuthorizationUrl(url)}),
      openAuthorizationUrl: async url => {
        const {default:open} = await import(pathToFileURL(require.resolve('open')).href);
        await open(safeAuthorizationUrl(url));
      },
    });
    emit(answer);
  } catch { emit({version:1,status:'adapter-error'}); }
  finally {
    clearTimeout(timer); clearTimeout(hardStop);
    process.removeListener('SIGINT',stop); process.removeListener('SIGTERM',stop);
  }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  await main(process.argv.slice(2));
  // A third-party server may leave handles after close; do not keep the UI alive.
  process.exit(0);
}
