"""Slack connector（組み込み）。User OAuth Token（xoxp-）貼り付け型＋検索ベースの決定論リーダー。

Slack Web API（https://slack.com/api）に `Authorization: Bearer <token>` ヘッダで叩く。依存追加
禁止のため HTTP は urllib のみ（transport 部分は connector_http.py に共通化して linear/github/
notion/chatwork と同じ形にしている）。

案内（`SLACK_MANIFEST`）: https://api.slack.com/apps で「Create New App → From an app manifest」を
選び、このマニフェストを貼り付けて自分のワークスペースにインストールし、発行された User OAuth
Token を貼り付けてもらう3段の wizard（connectors.py 側で guide として組み立てる）。

- 疎通確認（`verify`）は `POST /auth.test`。Slack API は **HTTP 200 でも body の `ok` が
  false** になり得るため、ステータスコードだけでなく必ず `ok` を検査する。成功時は
  `<user名>@<team名>`。
- 読み取り（`read`）は `search.messages` を2クエリ（`from:<@自分>` と `<@自分>`＝自分への
  メンション）叩き、`after:<since の日付>` を付けて絞る。自分の user_id は `auth.test` から
  取得する。2クエリの結果は ts で統合し、`uuid`（channel:ts）で重複排除してから昇順に返す。
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

from watari_cli import connector_http
from watari_cli.connectors import ConnectorError

AUTH_TEST_URL = "https://slack.com/api/auth.test"
SEARCH_URL = "https://slack.com/api/search.messages"

# guide の2段目でそのまま貼り付けてもらうマニフェスト（printable な定数として保持）。
SLACK_MANIFEST = """\
display_information:
  name: Watari
oauth_config:
  scopes:
    user:
      - search:read
"""


def _http(method: str, url: str, headers: dict | None = None, data: bytes | None = None):
    """(status, body_bytes) を返す。linear.py と同じ薄いラッパー（テストが差し替える名前）。"""
    return connector_http.request("slack", method, url, headers, data)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _call(token: str, method: str, url: str) -> dict:
    data = b"" if method == "POST" else None
    status, body = _http(method, url, _headers(token), data)
    if status == 401:
        raise ConnectorError("slack: 認証エラー（User OAuth Token を確認してください）")
    if status != 200:
        raise ConnectorError(f"slack: API エラー({status}): {body[:200]!r}")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise ConnectorError(f"slack: 応答が JSON ではありません: {body[:200]!r}")


def _auth_test(token: str) -> dict:
    """POST /auth.test。HTTP 200 でも ok:false があり得るので必ず ok を検査する。"""
    data = _call(token, "POST", AUTH_TEST_URL)
    if not data.get("ok"):
        raise ConnectorError(f"slack: {data.get('error') or '認証に失敗しました'}")
    return data


def verify(token: str) -> tuple[bool, str]:
    """疎通確認（auth.test）。成功時は (True, user名@team名)、失敗時は (False, 理由)。"""
    if not token:
        return False, "トークンが空です"
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


def _search(token: str, query: str) -> list[dict]:
    params = urllib.parse.urlencode(
        {"query": query, "sort": "timestamp", "sort_dir": "asc", "count": "100"})
    data = _call(token, "GET", f"{SEARCH_URL}?{params}")
    if not data.get("ok"):
        raise ConnectorError(f"slack: {data.get('error') or '検索に失敗しました'}")
    return ((data.get("messages") or {}).get("matches")) or []


def read(token: str, since: str | None) -> list[dict]:
    """カーソル(since)以降のメッセージ（自分の発言＋自分へのメンション）を統一形式
    [{ts,uuid,text,meta}, ...] で message_ts 昇順に返す。

    since 省略時は全件（呼び出し側＝connectors.read が host カーソルを既定として渡す）。
    """
    auth = _auth_test(token)
    user_id = auth.get("user_id")
    if not user_id:
        raise ConnectorError("slack: user_id が取得できませんでした")
    after_date = (since or "1970-01-01")[:10]

    matches = []
    matches += _search(token, f"from:<@{user_id}> after:{after_date}")
    matches += _search(token, f"<@{user_id}> after:{after_date}")

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
