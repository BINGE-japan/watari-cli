// Offline public API only. Never return raw server definitions or credentials.
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';
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
      name, status: def.disabled ? 'disabled' : 'configured',
      transport: def.url ? 'http' : def.socket ? 'socket' : 'stdio',
      endpoint: endpoint(def.url), authentication: def.auth || 'auto',
      lifecycle: def.lifecycle || 'lazy', approval: def.approveTools ?? config.settings?.approveTools ?? false,
      settings_override_file: provenance.get(name)?.path || null,
      metadata_status: valid ? 'cached' : 'unverified',
      tools: valid ? (entry.tools || []).slice(0, 1000).map(t => ({ name: t.name })) : [],
    };
  });
  process.stdout.write(JSON.stringify({ version: 1, servers, config_files: discovery.sources.filter(s => s.exists).map(s => s.path) }));
} catch {
  process.stderr.write('MCP configuration inspection failed.');
  process.exitCode = 1;
}
