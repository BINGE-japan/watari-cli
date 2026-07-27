"""Slack connector（組み込み）。User OAuth Token（xoxp-）貼り付け型＋検索ベースの決定論リーダー。

Slack Web API（https://slack.com/api）に `Authorization: Bearer <token>` ヘッダで叩く。依存追加
禁止のため HTTP は urllib のみ（transport 部分は connector_http.py に共通化して linear/github/
notion/chatwork と同じ形にしている）。

案内（`SLACK_MANIFEST`）: https://api.slack.com/apps →「Create New App」→「From an app manifest」
→ ワークスペース選択 → **既定で JSON タブが開き Demo App の雛形が入っているので全選択して置換**
→ Create → Install to Workspace → OAuth & Permissions の User OAuth Token（xoxp-）を貼る、という
実画面どおりの手順を connectors.py 側で guide として組み立てる。マニフェストを **JSON** で持つのは
その置換画面の既定タブが JSON だから（YAML に切り替えさせる手間を省く）。

- 疎通確認（`verify`）は `POST /auth.test`。Slack API は **HTTP 200 でも body の `ok` が
  false** になり得るため、ステータスコードだけでなく必ず `ok` を検査する。成功時は
  `<user名>@<team名>`。
- 読み取り（`read`）は `search.messages` を2クエリ（`from:<@自分>` と `<@自分>`＝自分への
  メンション）叩き、`after:<since の日付>` を付けて絞る。自分の user_id は `auth.test` から
  取得する。さらに監視チャンネル（config の `slack_watch_channels`、設定は
  `watari connector watch slack`）があれば `in:#<channel>` クエリをチャンネルごとに追加する
  ——発言とメンションだけでは、メンションなしの重要な投稿（スレッド内の相談など）を
  取りこぼすため。Slack 検索はスレッド返信も索引に含むので in:#channel で拾える。
  全クエリの結果は ts で統合し、`uuid`（channel:ts）で重複排除してから昇順に返す。
- 検索は1ページ100件・最大10ページまでめくる（100件超のサイレントな取りこぼし防止）。
- `after:` は日付粒度（YYYY-MM-DD）でしか絞れないため、since 当日に再取得すると同日分が
  再度返ってくる場合がある——それは呼び出し側の uuid dedup（host 側）に任せる。
- uuid は `slack:<channel_id>:<message_ts>`。ts は message_ts（epoch秒, 例 "1626339000.000200"）
  を UTC ISO8601 に変換する。
- text は `[#channel名] 発言者: 本文先頭200字`。
"""
from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone

from watari_cli import config, connector_http
from watari_cli.connectors import ConnectorError

AUTH_TEST_URL = "https://slack.com/api/auth.test"
SEARCH_URL = "https://slack.com/api/search.messages"

# 「Create app from manifest」の JSON タブへ全選択して貼り替えてもらうマニフェスト。
# Slack の必須項目は display_information.name のみ。ワタリが要るのは検索の読み取り(search:read)を
# 自分の権限で使う user scope だけで、bot も対話機能も要らない。
SLACK_MANIFEST = """\
{
  "display_information": {
    "name": "Watari"
  },
  "oauth_config": {
    "scopes": {
      "user": ["search:read"]
    }
  },
  "settings": {
    "org_deploy_enabled": false,
    "socket_mode_enabled": false,
    "token_rotation_enabled": false
  }
}
"""


def _http(method: str, url: str, headers: dict | None = None, data: bytes | None = None):
    """(status, body_bytes) を返す。linear.py と同じ薄いラッパー（テストが差し替える名前）。"""
    return connector_http.request("slack", method, url, headers, data)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _call(token: str, method: str, url: str) -> dict:
    data = b"" if method == "POST" else None
    status, body = _http(method, url, _headers(token), data)
    hint = connector_http.reconnect_hint("slack")
    if status == 401:
        raise ConnectorError(f"slack: 認証に失敗しました。{hint}")
    if status != 200:
        raise ConnectorError(
            f"slack: API エラー({status}): {connector_http.body_text(body)}。"
            f"時間をおいて再実行してください（続くようなら、{hint}）")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise ConnectorError(
            f"slack: 応答を読み取れませんでした: {connector_http.body_text(body)}。"
            f"時間をおいて再実行してください")


def _auth_test(token: str) -> dict:
    """POST /auth.test。HTTP 200 でも ok:false があり得るので必ず ok を検査する。"""
    data = _call(token, "POST", AUTH_TEST_URL)
    if not data.get("ok"):
        code = data.get("error") or "不明なエラー"
        raise ConnectorError(
            f"slack: 認証に失敗しました（{code}）。トークンが無効か取り消されています。"
            f"{connector_http.reconnect_hint('slack')}")
    return data


def verify(token: str) -> tuple[bool, str]:
    """疎通確認。まずトークンの形（xoxp- で始まるか）を検査してから auth.test を叩く。
    成功時は (True, user名@team名)、失敗時は (False, 理由)。

    auth.test は bot トークン（xoxb-）でも成功してしまい、初回の読み取りで初めて失敗する
    行き止まりになるため、貼り間違いはここで即座に弾いて正しい方を案内する。"""
    if not token:
        return False, "トークンが空です"
    if not token.startswith("xoxp-"):
        return False, ("これは User OAuth Token ではないようです。xoxp- で始まるトークンを"
                       "貼ってください（xoxb- で始まるのは bot 用で、読み取りに使えません）")
    try:
        data = _auth_test(token)
    except ConnectorError as error:
        return False, str(error)
    user = data.get("user") or "?"
    team = data.get("team") or "?"
    return True, f"{user}@{team}"


def _ts_to_iso(ts: str) -> str:
    dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


# 1クエリあたりの最大ページ数（1ページ100件）。件数の多い監視チャンネルで
# 100件を超えた分を黙って落とさないための上限付きページめくり。
_MAX_SEARCH_PAGES = 10


def _search(token: str, query: str) -> list[dict]:
    matches: list[dict] = []
    for page in range(1, _MAX_SEARCH_PAGES + 1):
        params = urllib.parse.urlencode(
            {"query": query, "sort": "timestamp", "sort_dir": "asc",
             "count": "100", "page": str(page)})
        data = _call(token, "GET", f"{SEARCH_URL}?{params}")
        if not data.get("ok"):
            code = data.get("error") or "不明なエラー"
            if code == "not_allowed_token_type":
                raise ConnectorError(
                    "slack: bot 用トークンでは読めません。watari connect slack で"
                    " User OAuth Token（xoxp- で始まる方）を貼り直してください")
            if code == "missing_scope":
                raise ConnectorError(
                    "slack: トークンに検索権限（search:read）がありません。"
                    "watari connect slack でアプリを作り直してください")
            raise ConnectorError(
                f"slack: 読み取りに失敗しました（{code}）。"
                f"{connector_http.reconnect_hint('slack')}")
        messages = data.get("messages") or {}
        matches.extend(messages.get("matches") or [])
        page_count = (messages.get("pagination") or {}).get("page_count") or 1
        if page >= page_count:
            break
    return matches


def read(token: str, since: str | None) -> list[dict]:
    """カーソル(since)以降のメッセージ（自分の発言＋自分へのメンション）を統一形式
    [{ts,uuid,text,meta}, ...] で message_ts 昇順に返す。

    since 省略時は全件（呼び出し側＝connectors.read が host カーソルを既定として渡す）。
    """
    auth = _auth_test(token)
    user_id = auth.get("user_id")
    if not user_id:
        raise ConnectorError(
            "slack: 自分のユーザー情報を取得できませんでした。"
            f"{connector_http.reconnect_hint('slack')}")
    after_date = (since or "1970-01-01")[:10]

    matches = []
    matches += _search(token, f"from:<@{user_id}> after:{after_date}")
    matches += _search(token, f"<@{user_id}> after:{after_date}")
    for channel in config.load_slack_watch_channels():
        matches += _search(token, f"in:#{channel} after:{after_date}")

    rows_by_uuid: dict[str, dict] = {}
    for match in matches:
        ts = match.get("ts")
        if not ts:
            continue
        channel = match.get("channel") or {}
        channel_id = channel.get("id") or "?"
        uuid = f"slack:{channel_id}:{ts}"
        if uuid in rows_by_uuid:
            continue
        if since and _ts_to_iso(ts) <= since:
            continue  # after: は日付粒度のため、since 当日のカーソル以前をここで絞る
        channel_name = channel.get("name") or channel_id
        speaker = match.get("username") or match.get("user") or "?"
        body = (match.get("text") or "").strip().replace("\n", " ")
        rows_by_uuid[uuid] = {
            "ts": _ts_to_iso(ts),
            "uuid": uuid,
            "text": f"[#{channel_name}] {speaker}: {body[:200]}",
            "meta": {"channel": channel_id, "ts": ts},
        }
    rows = list(rows_by_uuid.values())
    rows.sort(key=lambda r: (r["ts"], r["uuid"]))
    return rows
