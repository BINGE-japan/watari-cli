// Synthetic-only file loading and context construction through production helpers.
import { readFileSync } from 'node:fs';
import { loadMemoryContext, loadMemorySearch } from '../src/watari_cli/pi/memory-context.mjs';
import { performanceMemoryOptions } from '../src/watari_cli/pi/performance.mjs';

const queries = JSON.parse(readFileSync(0, 'utf8'));
const results = [];
for (const query of queries) {
  const search = await loadMemorySearch(process.env.WATARI_HOME, query.text, 6);
  const contexts = {};
  const context_bytes = {};
  for (const mode of ['fast', 'balanced', 'butler']) {
    contexts[mode] = await loadMemoryContext(
      process.env.WATARI_HOME, query.text, performanceMemoryOptions(mode),
    );
    context_bytes[mode] = Buffer.byteLength(JSON.stringify(contexts[mode]), 'utf8');
  }
  results.push({ ...query, search: search.matches, contexts, context_bytes });
}
console.log(JSON.stringify(results));
