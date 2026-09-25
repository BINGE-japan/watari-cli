// Offline public API only. Never return raw server definitions or credentials.
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';
import { connectionBinding, authHints, definitionFingerprint } from './mcp-management.mjs';
const [root, cwd] = process.argv.slice(2);
try {
  let warning = false;
  console.warn = () => { warning = true; };
  const api = await import(pathToFileURL(join(root, 'dist/config.js')).href);
  const metadata = await import(pathToFileURL(join(root, 'dist/metadata-cache.js')).href);
  const config = api.loadMcpConfig(undefined, cwd);
  const provenance = api.getServerProvenance(undefined, cwd);
  const discovery = api.getMcpStandardConfigSummary(undefined, cwd);
  const cache = metadata.loadMetadataCache();
  if (warning) throw new Error('Configuration could not be fully read');
  const endpoint = value => {
    if (typeof value !== 'string') return null;
    try { const u = new URL(value); return `${u.protocol}//${u.host}`; } catch { return '(変数を使用)'; }
  };
  const servers = Object.entries(config.mcpServers).map(([name, def]) => {
    const entry = cache?.servers?.[name];
    const valid = entry && metadata.isServerCacheValid(entry, def);
    return {
      ...authHints(def), definition_fingerprint: definitionFingerprint(def),
      name, status: def.disabled || def.enabled === false ? 'disabled' : 'configured',
      connection_binding: (() => { try { return connectionBinding(config, name, cwd, metadata); } catch { return null; } })(),
      transport: def.url ? 'http' : def.socket ? 'socket' : 'stdio',
      endpoint: endpoint(def.url), authentication: def.auth === false ? 'none' : def.auth || 'auto',
      lifecycle: def.lifecycle || 'lazy', approval: def.approveTools ?? config.settings?.approveTools ?? false,
      settings_override_file: provenance.get(name)?.path || null,
      metadata_status: valid ? 'cached' : 'unverified',
      tools: valid ? (entry.tools || []).slice(0, 1000).map(t => ({ name: t.name })) : [],
    };
  });
  const presets = (api.KNOWN_SERVER_PRESETS || []).filter(p => p.entry?.url).map(p => ({id:p.id,name:p.name,url:p.entry.url,...authHints(p.entry),auth:authHints(p.entry).oauth_setup_required ? 'bearer' : p.entry.auth || 'none'}));
  process.stdout.write(JSON.stringify({ version: 1, servers, presets, config_files: discovery.sources.filter(s => s.exists).map(s => s.path) }));
} catch {
  process.stderr.write('MCP configuration inspection failed.');
  process.exitCode = 1;
}
