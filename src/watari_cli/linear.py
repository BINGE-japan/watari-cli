"""Linear connector（組み込み第一弾）。Personal API key 認証＋issue の決定論リーダー。

GraphQL エンドポイント https://api.linear.app/graphql に `Authorization: <APIキー>` ヘッダで
POST する（Linear の Personal API key は Bearer 接頭辞を付けない）。依存追加禁止のため HTTP は
`urllib` のみ（cloud.py の _http と同じ形）。

- 疎通確認（`verify`）は `{ viewer { name email } }`。watari connect のその場確認に使う。
- 読み取り（`read`）は「自分が担当 or 作成した issue のうち updatedAt > since」を取得し、
  issue の現在値を統一形式 {ts, uuid, text, meta} の行に整形して updatedAt 昇順で返す
  （API 応答の順序に依存せずクライアント側で昇順に揃える）。
- uuid は `linear:<identifier>@<更新日YYYY-MM-DD>`（SCHEMA.md の dedup 規約と同一）。
- issue の中身は書き写さず、記憶に効く要点（identifier/title/state/dueDate/updatedAt/直近コメント
  要約）だけを text に畳む（正本は Linear のまま）。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from watari_cli.connectors import ConnectorError

API_URL = "https://api.linear.app/graphql"

VIEWER_QUERY = "{ viewer { name email } }"

# updatedAt は Linear の DateTimeOrDuration 比較（ISO ts を渡す）。assignee/creator どちらかが
# 自分の issue を対象にする。ページングは行わない（first 250 の単発取得。個人の担当/作成件数の
# 規模では十分。超える運用が出たら拡張）。
ISSUES_QUERY = """
query Issues($since: DateTimeOrDuration!) {
  issues(
    filter: {
      updatedAt: { gt: $since }
      or: [{ assignee: { isMe: { eq: true } } }, { creator: { isMe: { eq: true } } }]
    }
    first: 250
  ) {
    nodes {
      identifier
      title
      url
      updatedAt
      dueDate
      state { name }
      comments(last: 1) { nodes { body } }
    }
  }
}
"""


def _http(method: str, url: str, headers: dict | None = None, data: bytes | None = None):
    """(status, body_bytes) を返す。HTTP エラーは (code, body)、ネットワーク断は ConnectorError。"""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        raise ConnectorError(f"linear: ネットワークエラー: {e}")


def _post(api_key: str, query: str, variables: dict | None = None) -> dict:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    status, body = _http(
        "POST", API_URL,
        {"Content-Type": "application/json", "Authorization": api_key}, payload)
    if status == 401:
        raise ConnectorError("linear: 認証エラー（API キーを確認してください）")
    if status != 200:
        raise ConnectorError(f"linear: API エラー({status}): {body[:200]!r}")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise ConnectorError(f"linear: 応答が JSON ではありません: {body[:200]!r}")
    if parsed.get("errors"):
        messages = "; ".join(e.get("message", "") for e in parsed["errors"])
        raise ConnectorError(f"linear: {messages}")
    return parsed.get("data") or {}


def verify(api_key: str) -> tuple[bool, str]:
    """疎通確認（viewer クエリ）。成功時は (True, viewer名/email)、失敗時は (False, 理由)。"""
    if not api_key:
        return False, "API キーが空です"
    try:
        data = _post(api_key, VIEWER_QUERY)
    except ConnectorError as error:
        return False, str(error)
    viewer = data.get("viewer") or {}
    name = viewer.get("name") or viewer.get("email")
    if not name:
        return False, "viewer が取得できませんでした"
    return True, name


def _format_text(issue: dict) -> str:
    state = (issue.get("state") or {}).get("name") or "?"
    parts = [f"[{issue['identifier']}] {issue.get('title') or ''} (state={state})"]
    if issue.get("dueDate"):
        parts.append(f"due={issue['dueDate']}")
    parts.append(f"updated={issue['updatedAt']}")
    comments = (issue.get("comments") or {}).get("nodes") or []
    if comments:
        body = (comments[-1].get("body") or "").strip().replace("\n", " ")
        if body:
            parts.append(f"最新コメント: {body[:200]}")
    return " / ".join(parts)


def read(api_key: str, since: str | None) -> list[dict]:
    """カーソル(since)以降に更新された自分の issue を統一形式 [{ts,uuid,text,meta}, ...] で返す。

    since 省略時は全件（呼び出し側＝connectors.read が host カーソルを既定として渡す）。
    """
    variables = {"since": since or "1970-01-01T00:00:00.000Z"}
    data = _post(api_key, ISSUES_QUERY, variables)
    nodes = (data.get("issues") or {}).get("nodes") or []
    rows = []
    for issue in nodes:
        updated = issue["updatedAt"]
        day = updated[:10]
        rows.append({
            "ts": updated,
            "uuid": f"linear:{issue['identifier']}@{day}",
            "text": _format_text(issue),
            "meta": {"identifier": issue["identifier"], "url": issue.get("url")},
        })
    rows.sort(key=lambda r: (r["ts"], r["uuid"]))
    return rows
