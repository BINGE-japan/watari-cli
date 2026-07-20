"""GitHub connector（組み込み）。Personal Access Token（Fine-grained）認証＋issue/PR の決定論リーダー。

REST API（https://api.github.com）に `Authorization: Bearer <token>` ヘッダで叩く。依存追加禁止の
ため HTTP は urllib のみ（transport 部分は connector_http.py に共通化して linear/notion と三重複
しない形にしている）。

- 疎通確認（`verify`）は `GET /user`。login 名を返す。watari connect のその場確認に使う。
- 読み取り（`read`）は Search API（`GET /search/issues?q=involves:<login>+updated:><since>`）で
  「自分が関与する（author/assignee/mention/review 依頼など）issue・PR のうち since 以降に更新」を
  取得し、統一形式 {ts, uuid, text, meta} の行に整形して updated_at 昇順で返す（API 応答の順序に
  依存せずクライアント側で昇順に揃える）。
- ページングは 1 ページ（`per_page=100`）で打ち切り。これを超える件数が同一 since 区間に集中する
  運用はスコープ外（個人が since 以降に関与する issue/PR がこれを超える規模なら since を詰めて
  呼び直す）。
- uuid は `github:<owner/repo>#<number>@<更新日YYYY-MM-DD>`（SCHEMA.md の dedup 規約と同一）。
- issue/PR の中身は書き写さず、記憶に効く要点（repo#number/title/state/updated/comments 件数）
  だけを text に畳む（正本は GitHub のまま）。
"""
from __future__ import annotations

import json
import urllib.parse

from watari_cli import connector_http
from watari_cli.connectors import ConnectorError

API_BASE = "https://api.github.com"
SEARCH_URL = f"{API_BASE}/search/issues"

_ACCEPT = "application/vnd.github+json"


def _http(method: str, url: str, headers: dict | None = None, data: bytes | None = None):
    """(status, body_bytes) を返す。linear.py と同じ薄いラッパー（テストが差し替える名前）。"""
    return connector_http.request("github", method, url, headers, data)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": _ACCEPT, "User-Agent": "watari-cli"}


def _get(token: str, url: str) -> dict:
    status, body = _http("GET", url, _headers(token))
    if status == 401:
        raise ConnectorError("github: 認証エラー（Personal Access Token を確認してください）")
    if status != 200:
        raise ConnectorError(f"github: API エラー({status}): {body[:200]!r}")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise ConnectorError(f"github: 応答が JSON ではありません: {body[:200]!r}")


def verify(token: str) -> tuple[bool, str]:
    """疎通確認（GET /user）。成功時は (True, login名)、失敗時は (False, 理由)。"""
    if not token:
        return False, "トークンが空です"
    try:
        user = _get(token, f"{API_BASE}/user")
    except ConnectorError as error:
        return False, str(error)
    login = user.get("login")
    if not login:
        return False, "login が取得できませんでした"
    return True, login


def _to_search_ts(since: str) -> str:
    """カーソル ISO を GitHub 検索が受ける秒精度 ISO8601 (YYYY-MM-DDTHH:MM:SSZ) に丸める。"""
    base = since.replace("Z", "").split("+")[0].split(".")[0]
    return base + "Z" if "T" in base else base


def _repo_full_name(item: dict) -> str:
    return item.get("repository_url", "").split("/repos/", 1)[-1]


def _format_text(item: dict) -> str:
    repo = _repo_full_name(item)
    kind = "PR" if item.get("pull_request") else "Issue"
    parts = [f"[{repo}#{item['number']}] {item.get('title') or ''} (state={item.get('state')})"]
    parts.append(f"type={kind}")
    parts.append(f"updated={item['updated_at']}")
    comments = item.get("comments")
    if comments:
        parts.append(f"comments={comments}")
    return " / ".join(parts)


def read(token: str, since: str | None) -> list[dict]:
    """カーソル(since)以降に更新された、自分が関与する issue/PR を統一形式
    [{ts,uuid,text,meta}, ...] で updated_at 昇順に返す。

    since 省略時は全件（呼び出し側＝connectors.read が host カーソルを既定として渡す）。
    """
    user = _get(token, f"{API_BASE}/user")
    login = user.get("login")
    if not login:
        raise ConnectorError("github: login が取得できませんでした")
    # GitHub の検索修飾子 `updated:>` は秒精度まで。カーソルのミリ秒（...T05:07:01.176Z）を
    # そのまま渡すと 422 Unprocessable Entity になるため、秒に丸めてから渡す。
    since_q = _to_search_ts(since) if since else "1970-01-01T00:00:00Z"
    query = f"involves:{login} updated:>{since_q}"
    params = urllib.parse.urlencode(
        {"q": query, "sort": "updated", "order": "asc", "per_page": "100"})
    data = _get(token, f"{SEARCH_URL}?{params}")
    items = data.get("items") or []
    rows = []
    for item in items:
        updated = item["updated_at"]
        day = updated[:10]
        repo = _repo_full_name(item)
        rows.append({
            "ts": updated,
            "uuid": f"github:{repo}#{item['number']}@{day}",
            "text": _format_text(item),
            "meta": {"repo": repo, "number": item["number"], "url": item.get("html_url")},
        })
    rows.sort(key=lambda r: (r["ts"], r["uuid"]))
    return rows
