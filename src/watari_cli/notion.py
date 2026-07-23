"""Notion connector（組み込み）。Internal Integration Token 認証＋ページの決定論リーダー。

REST API（https://api.notion.com/v1）に `Authorization: Bearer <token>` `Notion-Version:
2022-06-28` ヘッダで叩く。依存追加禁止のため HTTP は urllib のみ（transport 部分は
connector_http.py に共通化して linear/github と三重複しない形にしている）。

- 疎通確認（`verify`）は `GET /users/me`。integration（bot）の名前と所属ワークスペースを返す。
  watari connect のその場確認に使う。
- 読み取り（`read`）は `POST /search`（`sort.timestamp=last_edited_time` を `descending`、
  `filter.value=page`）で「編集日時が古い順のページ」を取得し、`last_edited_time > since` を
  クライアント側で絞って統一形式 {ts, uuid, text, meta} に整形する（Notion の Search API は
  時刻レンジでの絞り込みクエリを持たないため、取得後にクライアント側で切る）。
- ページングは 1 リクエスト（`page_size=100`）で打ち切り。ワークスペース全体で編集済みページが
  これを超える規模だと、最初の1ページ（最も古い編集群から昇順）に since 以降の分がすべて
  現れない場合がある（スコープ制限。運用上問題になったら next_cursor を辿るよう拡張する）。
- uuid は `notion:<page_id>@<更新日YYYY-MM-DD>`（SCHEMA.md の dedup 規約と同一）。
- ページの中身は書き写さない（正本は Notion のまま）。text はタイトルと last_edited_time の
  ポインタだけに畳む。
"""
from __future__ import annotations

import json

from watari_cli import connector_http
from watari_cli.connectors import ConnectorError

API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _http(method: str, url: str, headers: dict | None = None, data: bytes | None = None):
    """(status, body_bytes) を返す。linear.py と同じ薄いラッパー（テストが差し替える名前）。"""
    return connector_http.request("notion", method, url, headers, data)


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _request(token: str, method: str, url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    status, body = _http(method, url, _headers(token), data)
    hint = connector_http.reconnect_hint("notion")
    if status == 401:
        raise ConnectorError(f"notion: 認証に失敗しました。シークレットが無効です。{hint}")
    if status != 200:
        raise ConnectorError(
            f"notion: API エラー({status}): {connector_http.body_text(body)}。"
            f"時間をおいて再実行してください（続くようなら、{hint}）")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise ConnectorError(
            f"notion: 応答を読み取れませんでした: {connector_http.body_text(body)}。"
            f"時間をおいて再実行してください")


# integration にページが1つも接続されていないと、認証は成功しても read が永遠に 0 件のまま
# 静かに空回りする。verify がその場で気づかせるための注意文（成功メッセージに添える）。
NO_PAGES_HINT = ("まだ読めるページがありません。Notion で読ませたいページを開き、"
                 "右上の『…』メニュー →『接続』から、作成した integration を追加してください")


def _readable_page_count(token: str) -> int | None:
    """search を1回だけ叩いて「integration から見えるページ数（先頭1件まで）」を返す。

    判定できないとき（search 自体の失敗）は None——verify の成否には影響させない。
    """
    try:
        data = _request(token, "POST", f"{API_BASE}/search", {"page_size": 1})
    except ConnectorError:
        return None
    return len(data.get("results") or [])


def verify(token: str) -> tuple[bool, str]:
    """疎通確認（GET /users/me → POST /search 1回）。成功時は (True, bot名/所属ワークスペース)、
    失敗時は (False, 理由)。読めるページが 0 件でも成功扱いのまま、メッセージに注意を含める
    （手順3の integration 接続を忘れると「成功したのに何も読めない」静かな失敗になるため）。"""
    if not token:
        return False, "トークンが空です"
    try:
        data = _request(token, "GET", f"{API_BASE}/users/me")
    except ConnectorError as error:
        return False, str(error)
    name = data.get("name") or "?"
    workspace = (data.get("bot") or {}).get("workspace_name")
    label = f"{name}（{workspace}）" if workspace else name
    if _readable_page_count(token) == 0:
        return True, f"{label}。※ {NO_PAGES_HINT}"
    return True, label


def _title(page: dict) -> str:
    props = page.get("properties") or {}
    for prop in props.values():
        if prop.get("type") == "title":
            texts = prop.get("title") or []
            joined = "".join(t.get("plain_text", "") for t in texts)
            if joined:
                return joined
    return "(無題)"


def _format_text(page: dict) -> str:
    return f"{_title(page)} / updated={page['last_edited_time']}"


def read(token: str, since: str | None) -> list[dict]:
    """カーソル(since)以降に編集されたページを統一形式 [{ts,uuid,text,meta}, ...] で
    last_edited_time 昇順に返す。

    Notion Search API に時刻フィルタがないため、**降順**で新しい方から 1 ページ（`page_size=100`）
    取得し、`last_edited_time > since` の分だけ拾って昇順に並べ直す（昇順取得だと「ワークスペースで
    最も古い 100 ページ」が返り、総数が 100 を超えると新しい編集が永遠に窓へ入らない）。
    since 以降の新規編集が 100 件を超える回はその回で取り切れない（カーソルが進めば次回続きが入る）。
    since 省略時は全件（呼び出し側＝connectors.read が host カーソルを既定として渡す）。
    """
    payload = {
        "sort": {"direction": "descending", "timestamp": "last_edited_time"},
        "filter": {"value": "page", "property": "object"},
        "page_size": 100,
    }
    data = _request(token, "POST", f"{API_BASE}/search", payload)
    results = data.get("results") or []
    since_q = since or "1970-01-01T00:00:00.000Z"
    rows = []
    for page in results:
        updated = page["last_edited_time"]
        if updated <= since_q:
            break  # 降順なのでこれ以降はすべて since 以前
        day = updated[:10]
        rows.append({
            "ts": updated,
            "uuid": f"notion:{page['id']}@{day}",
            "text": _format_text(page),
            "meta": {"id": page["id"], "url": page.get("url")},
        })
    rows.sort(key=lambda r: (r["ts"], r["uuid"]))
    return rows
