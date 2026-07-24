const STATE_KEY = Symbol.for("watari.verification-state");
const UNVERIFIED = "確認できる情報がないため、断定しません。";
const SPECULATION_WARNING = "⚠ この回答には推測表現が含まれています。";

export function verificationState() {
  if (!globalThis[STATE_KEY]) {
    globalThis[STATE_KEY] = {
      requiresObservation: false,
      evidenceAccepted: false,
      observedToolCalls: new Set(),
      observedTools: new Map(),
    };
  }
  return globalThis[STATE_KEY];
}

export function requiresObservation(input) {
  const text = String(input || "").trim();
  if (!text) return false;
  if (/^(?:こんにちは|こんばんは|おはようございます|ありがとう|ありがとうございます)[。.!！]?$/u.test(text)) {
    return false;
  }
  if (/(?:書き換えて|翻訳して|要約して|校正して|整形して|作って|生成して)[。.!！]?$/u.test(text) &&
      !/[？?]/u.test(text)) {
    return false;
  }
  return /[？?]/u.test(text) ||
    /(?:何|なに|どう|どの|どれ|誰|いつ|どこ|なぜ|何故|ですか|ますか|したか|できた|見て|確認して)/u.test(text);
}

function maskQuotedAndCode(text) {
  return text
    .replace(/```[\s\S]*?```/g, "")
    .replace(/`[^`\n]*`/g, "")
    .replace(/「[^」]*」/g, "")
    .replace(/『[^』]*』/g, "")
    .replace(/“[^”]*”/g, "")
    .replace(/"[^"\n]*"/g, "");
}

export function containsSpeculation(text) {
  const visible = maskQuotedAndCode(String(text || ""));
  return /(?:たぶん|多分|おそらく|恐らく|推測ですが|と思います|かもしれません|可能性があります|ようです|みたいです)/u.test(visible);
}

export function isClarifyingQuestion(text) {
  const value = String(text || "").trim();
  if (!/[？?]$/u.test(value)) return false;
  return /^(?:どの|どれ|何を指|どちらを指|対象は|具体的に|確認対象)/u.test(value);
}

export function guardAnswer(text, needsObservation, evidenceAccepted) {
  const value = String(text || "");
  if (containsSpeculation(value)) {
    return { text: `${value}\n\n${SPECULATION_WARNING}`, changed: true, blocked: false };
  }
  if (needsObservation && !evidenceAccepted && !isClarifyingQuestion(value)) {
    return { text: UNVERIFIED, changed: true, blocked: true };
  }
  return { text: value, changed: false, blocked: false };
}

export function guardVerifiedAssistantMessage(message) {
  const state = verificationState();
  let changed = false;
  const content = message.content.map((block) => {
    if (block.type !== "text") return block;
    const guarded = guardAnswer(
      block.text,
      state.requiresObservation,
      state.evidenceAccepted,
    );
    changed ||= guarded.changed;
    return guarded.changed ? { ...block, text: guarded.text } : block;
  });
  return changed ? { ...message, content } : message;
}
