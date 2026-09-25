import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage";

function configPath(env = process.env, home = homedir()) {
  const base = env.XDG_CONFIG_HOME || join(home, ".config");
  return join(base, "watari", "config.json");
}

export function loadSlackCredentials(env = process.env, home = homedir(), read = readFileSync) {
  let parsed;
  try {
    parsed = JSON.parse(read(configPath(env, home), "utf8"));
  } catch {
    throw new Error("Slackの投稿設定を読み取れません。ターミナルで `watari connect slack --legacy` を実行してください。");
  }
  const token = parsed?.connectors_auth?.slack?.bot_token;
  if (typeof token !== "string" || !token.startsWith("xoxb-")) {
    throw new Error("Watari botが未接続です。ターミナルで `watari connect slack --legacy` を実行してください。");
  }
  return { token, identity: parsed?.connectors_auth?.slack?.identity };
}

export function loadSlackBotToken(env = process.env, home = homedir(), read = readFileSync) {
  return loadSlackCredentials(env, home, read).token;
}

export async function verifySlackSender(credentials, request = fetch) {
  const { token, identity } = credentials;
  const keys = ["team_id", "bot_id", "user_id"];
  if (!identity || keys.some(key => typeof identity[key] !== "string" || !identity[key])
      || String(identity.name).toLowerCase() !== "watari") {
    throw new Error("Slackの送信者が未確認です。ターミナルで `watari connect slack --legacy` を実行してください。");
  }
  const response = await request("https://slack.com/api/auth.test", {
    method: "POST", headers: { Authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(15_000),
  });
  const actual = await response.json();
  if (!actual?.ok || keys.some(key => actual[key] !== identity[key]) || actual.user !== identity.name) {
    throw new Error("Slackの送信者が接続時と一致しないため、送信しません。接続し直してください。");
  }
  return identity;
}

function normalizedSlackText(text) {
  return String(text).replace(/<(https?:\/\/[^<>|]+)>/g, "$1");
}

function required(value, label) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${label}が空です。`);
  return value.trim();
}

function exactText(value) {
  if (typeof value !== "string" || !value.trim()) throw new Error("送信文面が空です。");
  return value;
}

export function approvalPreview(params, identity) {
  const destination = required(params.destination, "送信先の表示名");
  const recipient = required(params.recipient, "宛先");
  const channel = required(params.channel, "Slack channel ID");
  const text = exactText(params.text);
  const thread = params.thread_ts ? ` / thread ${params.thread_ts}` : " / 新規投稿";
  return [
    "送信元: Watari (Slack app)" + (identity ? ` / ${identity.team || identity.team_id} / bot ${identity.bot_id} / user ${identity.user_id}` : ""),
    `送信先: ${destination}`,
    `宛先: ${recipient}`,
    `実際の場所: ${channel}${thread}`,
    "",
    "送信する全文:",
    text,
  ].join("\n");
}

function slackErrorMessage(code) {
  if (code === "not_in_channel") {
    return "Watariがこのチャンネルに参加していません。Slackで @Watari をチャンネルへ招待してください。";
  }
  if (code === "missing_scope" || code === "invalid_auth" || code === "token_revoked") {
    return `Watari botの投稿権限を確認できません（${code}）。\`watari connect slack --legacy\` で接続し直してください。`;
  }
  return `Slackへの送信に失敗しました（${code || "unknown_error"}）。`;
}

export async function postSlackMessage(params, request = fetch) {
  const token = required(params.token, "Watari bot token");
  if (!token.startsWith("xoxb-")) throw new Error("Watari bot tokenの形式が不正です。");
  const channel = required(params.channel, "Slack channel ID");
  if (!/^[CG][A-Z0-9]+$/.test(channel)) {
    throw new Error("Slack channel IDの形式が不正です（チャンネルへの投稿だけに対応しています）。");
  }
  const text = exactText(params.text);
  if (text.length > 40_000) throw new Error("Slackへ送る文面が長すぎます（40000文字まで）。");
  const threadTs = params.threadTs ? required(params.threadTs, "Slack thread timestamp") : undefined;
  if (threadTs && !/^\d+\.\d+$/.test(threadTs)) throw new Error("Slack thread timestampの形式が不正です。");

  const body = {
    channel,
    text,
    ...(params.clientMsgId ? { client_msg_id: params.clientMsgId } : {}),
    ...(threadTs ? { thread_ts: threadTs } : {}),
  };
  const response = await request(SLACK_POST_MESSAGE_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json; charset=utf-8",
    },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!payload?.ok) throw new Error(slackErrorMessage(payload?.error));
  if (payload.channel !== channel || normalizedSlackText(payload.message?.text) !== normalizedSlackText(text)) {
    throw new Error("Slackの送信結果が承認した宛先または文面と一致しません。Slack画面を確認してください。");
  }
  if (params.identity && (payload.message?.bot_id !== params.identity.bot_id || payload.message?.user !== params.identity.user_id)) {
    throw new Error("Slackの投稿者を確認できません。再送せずSlack画面を確認してください。");
  }
  if (threadTs && payload.message?.thread_ts !== threadTs) {
    throw new Error("Slackの送信結果が承認したスレッドと一致しません。Slack画面を確認してください。");
  }
  return payload;
}
