import { readFile } from "node:fs/promises";
import { join } from "node:path";

export const DEFAULT_MAX_CONTEXT_BYTES = 16_000;
export const DEFAULT_MAX_PROFILE_BYTES = 5_000;
export const DEFAULT_MAX_ATTENTION_BYTES = 1_200;
export const DEFAULT_MAX_MATCHES_BYTES = 3_000;
export const DEFAULT_MAX_CATALOG_BYTES = 6_200;
const DEFAULT_MAX_MATCHES = 6;
const MAX_NOTE_CHARS = 360;
const MAX_ATTENTION_NOTE_CHARS = 240;
const COMMON_TERMS = new Set([
  "ある", "いる", "から", "こと", "この", "した", "して", "する", "その", "ため",
  "です", "どう", "ない", "なに", "ます", "まで", "もの", "よう", "れる",
]);
const BEHAVIOR_KEY_HINT = /(style|preference|tone|format|boundary|permission|communication|response|output|question|writing|instruction|説明|回答|応答|書式|文体|口調|確認|許可|禁止|好み|進め方|呼び方)/iu;
const BEHAVIOR_VALUE_HINT = /(必ず|禁止|しない|してください|してほしい|優先|回答|応答|確認して|許可)/u;

function normalize(value) {
  return String(value || "")
    .normalize("NFKC")
    .toLocaleLowerCase("und")
    .replace(/[^\p{L}\p{N}]+/gu, "");
}

function terms(value) {
  const raw = String(value || "").normalize("NFKC").toLocaleLowerCase("und");
  const compact = normalize(raw);
  const out = new Set(raw.match(/[a-z0-9][a-z0-9._+-]*/g) || []);
  if (compact.length <= 3) {
    if (compact) out.add(compact);
    return out;
  }
  for (const width of [2, 3]) {
    for (let index = 0; index <= compact.length - width; index += 1) {
      out.add(compact.slice(index, index + width));
    }
  }
  return out;
}

function documents(life, learning) {
  const docs = [];
  for (const [topic, item] of Object.entries(life?.facts || {})) {
    docs.push({ kind: "fact", topic, value: item || {} });
  }
  for (const item of life?.open_threads || []) {
    if (!item?.topic) continue;
    docs.push({ kind: "thread", topic: item.topic, value: item });
  }
  for (const [topic, item] of Object.entries(life?.interests || {})) {
    docs.push({ kind: "interest", topic, value: item || {} });
  }
  for (const [domain, group] of Object.entries(learning?.domains || {})) {
    for (const [topic, item] of Object.entries(group?.topics || {})) {
      docs.push({ kind: "study", domain, topic, value: item || {} });
    }
  }
  return docs;
}

function searchableText(doc) {
  return [
    doc.kind,
    doc.domain || "",
    doc.topic,
    doc.value?.note || "",
    ...(doc.value?.tags || []),
    ...(doc.value?.related || []),
  ].join(" ");
}

function rank(docs, query, limit) {
  const queryNormalized = normalize(query);
  const queryTerms = new Set([...terms(query)].filter((term) => !COMMON_TERMS.has(term)));
  if (!queryNormalized || queryTerms.size === 0) return [];

  const prepared = docs.map((doc, order) => ({
    doc,
    order,
    topicNormalized: normalize(doc.topic),
    topicTerms: new Set([...terms(doc.topic)].filter((term) => !COMMON_TERMS.has(term))),
    bodyTerms: new Set([...terms(searchableText(doc))].filter((term) => !COMMON_TERMS.has(term))),
  }));
  const frequencies = new Map();
  for (const item of prepared) {
    for (const term of item.bodyTerms) {
      frequencies.set(term, (frequencies.get(term) || 0) + 1);
    }
  }
  const rareLimit = Math.max(1, Math.floor(docs.length * 0.08));
  const weight = (term) => 1 + Math.log((docs.length + 1) / ((frequencies.get(term) || 0) + 1));

  return prepared
    .map((item) => {
      const exact = (queryNormalized.length >= 2 && item.topicNormalized.includes(queryNormalized))
        || (item.topicNormalized.length >= 2 && queryNormalized.includes(item.topicNormalized));
      const topicShared = [...queryTerms].filter((term) => item.topicTerms.has(term));
      const bodyShared = [...queryTerms].filter((term) => item.bodyTerms.has(term));
      const hasStrongEvidence = exact
        || topicShared.some((term) => term.length >= 3)
        || topicShared.some((term) => (frequencies.get(term) || 0) <= rareLimit)
        || bodyShared.some((term) => term.length >= 3);
      if (!hasStrongEvidence) return { ...item, score: 0 };

      let score = exact ? 80 : 0;
      for (const term of bodyShared) score += weight(term);
      for (const term of topicShared) score += weight(term) * 4;
      return { ...item, score };
    })
    .filter((item) => item.score >= 3)
    .sort((left, right) => right.score - left.score || left.order - right.order)
    .slice(0, limit)
    .map((item) => item.doc);
}

function clipped(value, max = MAX_NOTE_CHARS) {
  const text = String(value || "");
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}

function outputEntry(doc, noteLimit = MAX_NOTE_CHARS) {
  const value = doc.value || {};
  const base = {
    kind: doc.kind,
    ...(doc.domain ? { domain: doc.domain } : {}),
    topic: doc.topic,
    ...(value.note ? { note: clipped(value.note, noteLimit) } : {}),
    ...(value.last ? { last: value.last } : {}),
  };
  if (doc.kind === "thread") {
    if (value.deadline) base.deadline = value.deadline;
    if (value.dormant) base.dormant = true;
  } else if (doc.kind === "interest") {
    if (Number.isInteger(value.heat)) base.heat = value.heat;
  } else if (doc.kind === "study") {
    if (Number.isInteger(value.mastery)) base.mastery = value.mastery;
    if (value.freshness) base.freshness = value.freshness;
    if (Array.isArray(value.related) && value.related.length) {
      base.related = value.related.slice(0, 6);
    }
  }
  return base;
}

function attentionThreads(life, limit = 3) {
  return [...(life?.open_threads || [])]
    .filter((item) => item?.topic)
    .sort((left, right) => {
      const leftDeadline = left.deadline || "9999";
      const rightDeadline = right.deadline || "9999";
      if (leftDeadline !== rightDeadline) return leftDeadline.localeCompare(rightDeadline);
      if (Boolean(left.dormant) !== Boolean(right.dormant)) return left.dormant ? -1 : 1;
      return String(right.last || "").localeCompare(String(left.last || ""));
    })
    .slice(0, limit)
    .map((item) => outputEntry(
      { kind: "thread", topic: item.topic, value: item },
      MAX_ATTENTION_NOTE_CHARS,
    ));
}

function sortedObject(input) {
  return Object.fromEntries(
    Object.entries(input || {}).sort(([left], [right]) => left.localeCompare(right)),
  );
}

function makeCatalog(docs, profileKeys = []) {
  const catalog = { profiles: [...profileKeys].sort(), facts: [], threads: [], interests: [], learning: {} };
  for (const doc of docs) {
    if (doc.kind === "fact") catalog.facts.push(doc.topic);
    else if (doc.kind === "thread") catalog.threads.push(doc.topic);
    else if (doc.kind === "interest") catalog.interests.push(doc.topic);
    else (catalog.learning[doc.domain] ||= []).push(doc.topic);
  }
  catalog.facts.sort();
  catalog.threads.sort();
  catalog.interests.sort();
  catalog.learning = sortedObject(catalog.learning);
  for (const topics of Object.values(catalog.learning)) topics.sort();
  return catalog;
}

function emptyCatalog() {
  return { profiles: [], facts: [], threads: [], interests: [], learning: {} };
}

function byteLength(value) {
  return Buffer.byteLength(JSON.stringify(value), "utf8");
}

function fitProfile(input, maxBytes) {
  const entries = Object.entries(input).map(([key, value]) => ({
    key,
    value,
    // 旧記録が未分類で溢れたときだけ使う安全網。新記録は profile.mode で明示分類する。
    priority: (BEHAVIOR_KEY_HINT.test(key) ? 100 : 0)
      + (BEHAVIOR_VALUE_HINT.test(String(value)) ? 50 : 0),
  }));
  entries.sort((left, right) => right.priority - left.priority || left.key.localeCompare(right.key));
  const selected = {};
  let truncated = false;
  for (const { key, value } of entries) {
    selected[key] = value;
    if (byteLength(selected) <= maxBytes) continue;
    delete selected[key];
    truncated = true;
  }
  return { profile: sortedObject(selected), truncated };
}

function fitArray(items, maxBytes, minimum = 0) {
  const output = [...items];
  while (output.length > minimum && byteLength(output) > maxBytes) output.pop();
  return output;
}

function removeLastCatalogTopic(catalog) {
  const domains = Object.keys(catalog.learning).reverse();
  for (const domain of domains) {
    const topics = catalog.learning[domain];
    if (topics.length) {
      topics.pop();
      if (!topics.length) delete catalog.learning[domain];
      return true;
    }
  }
  if (catalog.interests.length) {
    catalog.interests.pop();
    return true;
  }
  if (catalog.facts.length) {
    catalog.facts.pop();
    return true;
  }
  if (catalog.profiles.length) {
    catalog.profiles.pop();
    return true;
  }
  if (catalog.threads.length) {
    catalog.threads.pop();
    return true;
  }
  return false;
}

function fitCatalog(catalog, maxBytes) {
  while (byteLength(catalog) > maxBytes && removeLastCatalogTopic(catalog)) {}
  return catalog;
}

function fitToBudget(context, maxBytes) {
  while (byteLength(context) > maxBytes && removeLastCatalogTopic(context.catalog)) {
    context.catalog_truncated = true;
  }
  while (byteLength(context) > maxBytes && context.matches.length > 1) context.matches.pop();
  while (byteLength(context) > maxBytes && context.attention.length > 1) context.attention.pop();
  while (byteLength(context) > maxBytes && Object.keys(context.profile).length > 1) {
    delete context.profile[Object.keys(context.profile).at(-1)];
    context.profile_truncated = true;
  }
  if (byteLength(context) > maxBytes) {
    context.catalog = emptyCatalog();
    context.catalog_truncated = true;
    context.attention = context.attention.slice(0, 1);
    context.matches = context.matches.slice(0, 1).map((item) => ({
      ...item,
      ...(item.note ? { note: clipped(item.note, 120) } : {}),
    }));
  }
  return context;
}

export function buildMemoryContext(life, learning, query, options = {}) {
  if (options.full) {
    return {
      memory_checked: true,
      full_context: true,
      profile: sortedObject(life?.profile || {}),
      life: {
        updated: life?.updated,
        facts: life?.facts || {},
        interests: life?.interests || {},
        open_threads: life?.open_threads || [],
      },
      learning: learning || {},
    };
  }

  const maxBytes = options.maxBytes ?? DEFAULT_MAX_CONTEXT_BYTES;
  const maxMatches = options.maxMatches ?? DEFAULT_MAX_MATCHES;
  const attentionLimit = options.attentionLimit ?? 3;
  const includeCatalog = options.includeCatalog !== false;
  const profileMaxBytes = options.profileMaxBytes ?? Math.min(DEFAULT_MAX_PROFILE_BYTES, maxBytes * 0.34);
  const attentionMaxBytes = options.attentionMaxBytes ?? Math.min(DEFAULT_MAX_ATTENTION_BYTES, maxBytes * 0.10);
  const matchesMaxBytes = options.matchesMaxBytes ?? Math.min(DEFAULT_MAX_MATCHES_BYTES, maxBytes * 0.22);
  const catalogMaxBytes = includeCatalog
    ? options.catalogMaxBytes ?? Math.min(DEFAULT_MAX_CATALOG_BYTES, maxBytes * 0.40)
    : 0;

  const allProfile = sortedObject(life?.profile || {});
  const fittedProfile = fitProfile(allProfile, profileMaxBytes);
  const docs = documents(life, learning);
  const attention = fitArray(attentionThreads(life, attentionLimit), attentionMaxBytes, 1);
  const matches = fitArray(
    rank(docs, query, maxMatches).map((doc) => outputEntry(doc)),
    matchesMaxBytes,
    1,
  );
  const catalog = includeCatalog
    ? fitCatalog(makeCatalog(docs, Object.keys(allProfile)), catalogMaxBytes)
    : emptyCatalog();
  const fullCatalog = includeCatalog ? makeCatalog(docs, Object.keys(allProfile)) : emptyCatalog();
  const context = {
    memory_checked: true,
    profile: fittedProfile.profile,
    profile_truncated: fittedProfile.truncated,
    attention,
    matches,
    catalog,
    catalog_truncated: includeCatalog && byteLength(catalog) < byteLength(fullCatalog),
  };
  return fitToBudget(context, maxBytes);
}

async function readJson(path, fallback) {
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") return fallback;
    throw error;
  }
}

export async function loadMemoryContext(home, query, options = {}) {
  if (!home) throw new Error("WATARI_HOME is not set");
  const [life, learning] = await Promise.all([
    readJson(join(home, "life", "state.json"), {}),
    readJson(join(home, "learning", "state.json"), {}),
  ]);
  return buildMemoryContext(life, learning, query, options);
}
