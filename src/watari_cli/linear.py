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

from watari_cli import connector_http
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

BRIEF_ISSUES_QUERY = """
query BriefIssues {
  issues(filter: { assignee: { isMe: { eq: true } } }, first: 250) {
    nodes {
      identifier
      title
      url
      dueDate
      state { name type }
    }
  }
}
"""


def _http(method: str, url: str, headers: dict | None = None, data: bytes | None = None):
    """(status, body_bytes) を返す。HTTP エラーは (code, body)、ネットワーク断は ConnectorError。

    urllib の transport 部分は connector_http.py に共通化済み（github/notion と共有）。
    テストが `linear._http` を丸ごと差し替えられるよう、薄いラッパーとしてこの名前を残す。
    """
    return connector_http.request("linear", method, url, headers, data)


def _post(api_key: str, query: str, variables: dict | None = None) -> dict:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    status, body = _http(
        "POST", API_URL,
        {"Content-Type": "application/json", "Authorization": api_key}, payload)
    hint = connector_http.reconnect_hint("linear")
    if status == 401:
        raise ConnectorError(
            f"linear: 認証に失敗しました。API キーが無効か削除されています。{hint}")
    if status != 200:
        raise ConnectorError(
            f"linear: API エラー({status}): {connector_http.body_text(body)}。"
            f"時間をおいて再実行してください（続くようなら、{hint}）")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise ConnectorError(
            f"linear: 応答を読み取れませんでした: {connector_http.body_text(body)}。"
            f"時間をおいて再実行してください")
    if parsed.get("errors"):
        messages = "; ".join(e.get("message", "") for e in parsed["errors"])
        raise ConnectorError(f"linear: {messages}（{hint}）")
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
        return False, ("アカウント情報を取得できませんでした。API キーの権限を確認してください"
                       f"（{connector_http.reconnect_hint('linear')}）")
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


def brief(api_key: str, now) -> list[dict]:
    """Observe assigned, open issues due within seven days; never mutate Linear."""
    from datetime import date

    from watari_cli.briefing import _signal, rank_signals

    data = _post(api_key, BRIEF_ISSUES_QUERY)
    signals = []
    today = now.date()
    for issue in (data.get("issues") or {}).get("nodes") or []:
        state_type = ((issue.get("state") or {}).get("type") or "").lower()
        if state_type in ("completed", "canceled") or not issue.get("dueDate"):
            continue
        try:
            due = date.fromisoformat(issue["dueDate"])
        except ValueError:
            continue
        days = (due - today).days
        if days < 0:
            urgency, reason = 3, "期限が過ぎています"
        elif days == 0:
            urgency, reason = 3, "期限は今日です"
        elif days <= 7:
            urgency, reason = 2, "期限まで7日以内です"
        else:
            continue
        identifier = issue.get("identifier") or "?"
        signals.append(_signal(
            signal_id=f"linear:issue:{identifier}", kind="deadline", source="linear",
            urgency=urgency, title=f"{identifier} {issue.get('title') or ''}".strip(),
            reason=reason, due_at=f"{due.isoformat()}T23:59:59.000Z",
            pointer=issue.get("url"),
        ))
    return rank_signals(signals)


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
