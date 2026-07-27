import { readFile } from "node:fs/promises";
import { join } from "node:path";

export const DEFAULT_MAX_CONTEXT_BYTES = 16_000;
const DEFAULT_MAX_MATCHES = 6;
const MAX_NOTE_CHARS = 700;

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

function overlap(left, right) {
  let count = 0;
  for (const term of left) {
    if (right.has(term)) count += term.length >= 4 ? 2 : 1;
  }
  return count;
}

function documents(life, learning) {
  const docs = [];
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
    ...(doc.value?.related || []),
  ].join(" ");
}

function rank(docs, query, limit) {
  const queryNormalized = normalize(query);
  const queryTerms = terms(query);
  if (!queryNormalized || queryTerms.size === 0) return [];

  return docs
    .map((doc, order) => {
      const topicNormalized = normalize(doc.topic);
      const topicTerms = terms(doc.topic);
      const bodyTerms = terms(searchableText(doc));
      let score = overlap(queryTerms, bodyTerms) + overlap(queryTerms, topicTerms) * 3;
      if (queryNormalized.length >= 2 && topicNormalized.includes(queryNormalized)) score += 80;
      if (topicNormalized.length >= 2 && queryNormalized.includes(topicNormalized)) score += 50;
      return { doc, order, score };
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

function outputEntry(doc) {
  const value = doc.value || {};
  const base = {
    kind: doc.kind,
    ...(doc.domain ? { domain: doc.domain } : {}),
    topic: doc.topic,
    ...(value.note ? { note: clipped(value.note) } : {}),
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
    .map((item) => outputEntry({ kind: "thread", topic: item.topic, value: item }));
}

function sortedObject(input) {
  return Object.fromEntries(
    Object.entries(input || {}).sort(([left], [right]) => left.localeCompare(right)),
  );
}

function makeCatalog(docs) {
  const catalog = { threads: [], interests: [], learning: {} };
  for (const doc of docs) {
    if (doc.kind === "thread") catalog.threads.push(doc.topic);
    else if (doc.kind === "interest") catalog.interests.push(doc.topic);
    else {
      (catalog.learning[doc.domain] ||= []).push(doc.topic);
    }
  }
  catalog.threads.sort();
  catalog.interests.sort();
  catalog.learning = sortedObject(catalog.learning);
  for (const topics of Object.values(catalog.learning)) topics.sort();
  return catalog;
}

function byteLength(value) {
  return Buffer.byteLength(JSON.stringify(value), "utf8");
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
  if (catalog.threads.length) {
    catalog.threads.pop();
    return true;
  }
  return false;
}

function fitToBudget(context, maxBytes) {
  while (byteLength(context) > maxBytes && removeLastCatalogTopic(context.catalog)) {
    context.catalog_truncated = true;
  }
  while (byteLength(context) > maxBytes && context.matches.length > 1) {
    context.matches.pop();
  }
  while (byteLength(context) > maxBytes && context.attention.length > 1) {
    context.attention.pop();
  }
  if (byteLength(context) > maxBytes) {
    context.profile = Object.fromEntries(
      Object.entries(context.profile).map(([key, value]) => [key, clipped(value, 240)]),
    );
  }
  while (byteLength(context) > maxBytes && Object.keys(context.profile).length > 1) {
    delete context.profile[Object.keys(context.profile).at(-1)];
  }
  // Defensive final bound for pathological single values.
  if (byteLength(context) > maxBytes) {
    context.catalog = { threads: [], interests: [], learning: {} };
    context.catalog_truncated = true;
    context.attention = context.attention.slice(0, 1);
    context.matches = context.matches.slice(0, 1).map((item) => ({
      ...item,
      ...(item.note ? { note: clipped(item.note, 160) } : {}),
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
        interests: life?.interests || {},
        open_threads: life?.open_threads || [],
      },
      learning: learning || {},
    };
  }

  const maxBytes = options.maxBytes ?? DEFAULT_MAX_CONTEXT_BYTES;
  const maxMatches = options.maxMatches ?? DEFAULT_MAX_MATCHES;
  const attentionLimit = options.attentionLimit ?? 3;
  const docs = documents(life, learning);
  const context = {
    memory_checked: true,
    profile: sortedObject(life?.profile || {}),
    attention: attentionThreads(life, attentionLimit),
    matches: rank(docs, query, maxMatches).map(outputEntry),
    catalog: options.includeCatalog === false
      ? { threads: [], interests: [], learning: {} }
      : makeCatalog(docs),
    catalog_truncated: false,
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
