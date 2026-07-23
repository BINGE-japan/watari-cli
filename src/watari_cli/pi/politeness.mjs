const BLOCKED_RESPONSE =
  "申し訳ありません。敬語ではない応答を検出したため、回答を表示しませんでした。";

function maskQuotedAndCode(text) {
  return text
    .replace(/```[\s\S]*?```/g, "")
    .replace(/`[^`\n]*`/g, "")
    .replace(/「[^」]*」/g, "")
    .replace(/『[^』]*』/g, "")
    .replace(/“[^”]*”/g, "")
    .replace(/"[^"\n]*"/g, "");
}

function rewriteKnownCasual(text) {
  return text
    .replace(/^(\s*)(?:おす|押忍|うす)(?=[、,。.!！\s]|$)/u, "$1こんにちは")
    .replace(/今日は何やります[？?]?/gu, "今日は何をしますか。")
    .replace(/何やります[？?]/gu, "何をしますか。")
    .replace(/^\s*了解(?:です)?[。.!！]?\s*$/u, "承知しました。")
    .replace(/^\s*うん[。.!！]?\s*$/u, "はい。")
    .replace(/^\s*ありがとう[。.!！]?\s*$/u, "ありがとうございます。");
}

function containsCasualJapanese(text) {
  const visible = maskQuotedAndCode(text);
  const patterns = [
    /(?:^|[。！？!?\n]\s*)(?:おす|押忍|うす|よっ|やあ|うん|了解|オッケー|いいよ|任せて)(?=[、,。！？!?\s]|$)/u,
    /(?:だよ|だね|だぞ|だな|じゃん|するよ|やるよ|しよう|やろう|いいよ|任せて)(?:[。！？!?]|$)/u,
    /(?:何する|どうする|何やる|何やります)(?:[？?]|$)/u,
    /(?:^|[。！？!?\n]\s*)(?:ごめん|ありがと)(?=[、,。！？!?\s]|$)/u,
  ];
  return patterns.some((pattern) => pattern.test(visible));
}

export function guardText(text) {
  const rewritten = rewriteKnownCasual(text);
  if (containsCasualJapanese(rewritten)) {
    return { text: BLOCKED_RESPONSE, changed: true, blocked: true };
  }
  return {
    text: rewritten,
    changed: rewritten !== text,
    blocked: false,
  };
}

export function guardAssistantMessage(message) {
  let changed = false;
  const content = message.content.map((block) => {
    if (block.type !== "text") return block;
    const guarded = guardText(block.text);
    changed ||= guarded.changed;
    return guarded.changed ? { ...block, text: guarded.text } : block;
  });
  return changed ? { ...message, content } : message;
}
