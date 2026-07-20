"""Google 系の組み込みコネクタ（gmail / calendar / gdrive）を1ファイルにまとめる。

linear/github/notion と違い、この3つは認証がトークン貼り付けではなく **cloud.py が持つ Google
OAuth（drive.appdata 用に既に確立済み）の incremental scope 拡張**を共有する。個別のトークン
文字列を connectors_auth に保存する代わりに、サービスごとの verify が「必要スコープが
`cloud.granted_scopes()` に含まれるか」を見て、無ければ `cloud.authorize([必要スコープ])` を
その場で起動してブラウザ承認を求める（既存の drive.appdata 権限や他サービスの権限は
`include_granted_scopes=true` により失われない）。read はアクセストークンだけを使う
（`cloud.access_token()`）ので、この3サービスは connectors.py の ServiceAdapter に
`auth_kind="oauth"` を持たせて呼び分ける（connectors.read/is_connected 側で分岐、サービス名の
if/elif はどこにも書かない）。

HTTP は他アダプタと同じく urllib のみ（`connector_http.py` 経由）。トランスポートは3サービス共通の
`_http` を1つ持つ（テストはこれを差し替える）。認証エラー(401)/権限エラー(403・スコープ不足の
可能性を案内)は ConnectorError にまとめる。

各サービスの中身は書き写さない（正本は Gmail/Calendar/Drive のまま）: 要点だけを text に畳む。
"""
from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone

from watari_cli import cloud, connector_http
from watari_cli.connectors import ConnectorError

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
GDRIVE_SCOPE = "https://www.googleapis.com/auth/drive.metadata.readonly"

GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"
DRIVE_API = "https://www.googleapis.com/drive/v3"

# カーソル未設定（初回接続）の既定。1970 年にすると全履歴を一度に引き込み、夢が過去の
# 全ファイル/全メールを再判定する羽目になる。初回は直近 INITIAL_LOOKBACK_DAYS 日だけ見る
# （以後はカーソルが進むので窓は自然に閉じる）。
INITIAL_LOOKBACK_DAYS = 14


def _default_since() -> str:
    from datetime import timedelta

    from watari_cli.engine.watari_lib import fmt_ts, now_utc

    return fmt_ts(now_utc() - timedelta(days=INITIAL_LOOKBACK_DAYS))


_EPOCH = "1970-01-01T00:00:00.000Z"


def _http(method: str, url: str, headers: dict | None = None, data: bytes | None = None):
    """(status, body_bytes) を返す。他アダプタと同じ薄いラッパー（テストが差し替える名前）。"""
    return connector_http.request("google", method, url, headers, data)


def _raise_for_status(service: str, status: int, body: bytes) -> None:
    if status == 401:
        raise ConnectorError(
            f"{service}: 認証エラー（Google の認可が失効しています。`watari connect {service}` で再承認）")
    if status == 403:
        raise ConnectorError(
            f"{service}: 権限エラー(403)。スコープ不足、または同梱の OAuth アプリを承認できない"
            f"アカウントの可能性があります（docs/google-oauth-setup.md の Internal/自分のアプリ登録を参照）"
            f"（`watari connect {service}` で権限を再承認してください）: {body[:200]!r}")
    if status != 200:
        raise ConnectorError(f"{service}: API エラー({status}): {body[:200]!r}")


def _get_json(service: str, url: str, token: str) -> dict:
    status, body = _http("GET", url, {"Authorization": f"Bearer {token}"})
    _raise_for_status(service, status, body)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise ConnectorError(f"{service}: 応答が JSON ではありません: {body[:200]!r}")


def _ensure_scope_and_describe(scope: str, describe) -> tuple[bool, str]:
    """必要スコープが未付与なら cloud.authorize([scope]) でブラウザ承認 → describe() の結果を返す。

    describe は「疎通確認用の1発呼び出し（プロフィール等を返す）」。ConnectorError/CloudError は
    ここで (False, message) に畳む（`watari connect` の呼び出し元は例外を気にしなくてよい）。
    """
    if scope not in cloud.granted_scopes():
        ok, message = cloud.authorize([scope])
        if not ok:
            return False, message
    try:
        return True, describe()
    except (ConnectorError, cloud.CloudError) as error:
        return False, str(error)


# ---- gmail ------------------------------------------------------------------

def _gmail_profile_email() -> str:
    data = _get_json("gmail", f"{GMAIL_API}/users/me/profile", cloud.access_token())
    return data.get("emailAddress") or "?"


def gmail_verify() -> tuple[bool, str]:
    """必要スコープ gmail.readonly の確認（無ければブラウザ承認）→ profile の emailAddress。"""
    return _ensure_scope_and_describe(GMAIL_SCOPE, _gmail_profile_email)


def _epoch_seconds(ts: str | None) -> int:
    if not ts:
        return 0
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _iso_from_epoch_millis(ms: str | int | None) -> str:
    try:
        dt = datetime.fromtimestamp(int(ms or 0) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        dt = datetime.fromtimestamp(0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def gmail_read(since: str | None) -> list[dict]:
    """since 以降のメール一覧を統一形式 [{ts,uuid,text,meta}, ...] で internalDate 昇順に返す。

    messages.list は `q=after:<epoch秒>` で絞り込み、maxResults=100 まで一覧を取ってから、
    本文は取らずヘッダ(From/Subject/Date)+snippet だけを1リクエストずつ(format=metadata)取得する
    （50件/回で打ち切り、超過分は次回の呼び出しに回る＝linear/github と同じ「1回で取り切らない」
    設計）。since 省略時（初回接続）は直近 INITIAL_LOOKBACK_DAYS 日だけ見る。
    """
    token = cloud.access_token()
    q = urllib.parse.urlencode(
        {"q": f"after:{_epoch_seconds(since or _default_since())}", "maxResults": "100"})
    listing = _get_json("gmail", f"{GMAIL_API}/users/me/messages?{q}", token)
    ids = [m["id"] for m in (listing.get("messages") or [])][:50]

    header_params = urllib.parse.urlencode(
        [("format", "metadata"), ("metadataHeaders", "From"),
         ("metadataHeaders", "Subject"), ("metadataHeaders", "Date")])
    rows = []
    for message_id in ids:
        msg = _get_json(
            "gmail", f"{GMAIL_API}/users/me/messages/{message_id}?{header_params}", token)
        headers = {h.get("name"): h.get("value")
                  for h in (msg.get("payload") or {}).get("headers") or []}
        ts = _iso_from_epoch_millis(msg.get("internalDate"))
        day = ts[:10]
        frm = headers.get("From") or "?"
        subject = headers.get("Subject") or "(件名なし)"
        snippet = (msg.get("snippet") or "").strip()
        rows.append({
            "ts": ts,
            "uuid": f"gmail:{message_id}@{day}",
            "text": f"From: {frm} / Subject: {subject} / {snippet}",
            "meta": {"id": message_id, "threadId": msg.get("threadId")},
        })
    rows.sort(key=lambda r: (r["ts"], r["uuid"]))
    return rows


# ---- calendar -----------------------------------------------------------------

def _calendar_primary_summary() -> str:
    data = _get_json("calendar", f"{CALENDAR_API}/calendars/primary", cloud.access_token())
    return data.get("summary") or data.get("id") or "?"


def calendar_verify() -> tuple[bool, str]:
    """必要スコープ calendar.readonly の確認（無ければブラウザ承認）→ primary カレンダーの表示名。"""
    return _ensure_scope_and_describe(CALENDAR_SCOPE, _calendar_primary_summary)


def calendar_read(since: str | None) -> list[dict]:
    """primary カレンダーの since 以降の更新イベントを統一形式で updated 昇順に返す。

    events.list(updatedMin=since, maxResults=100, showDeleted=true) の単発取得（ページングなし。
    since 以降の更新がこれを超える規模は運用スコープ外＝他アダプタと同じ前提）。
    since 省略時（初回接続）は直近 INITIAL_LOOKBACK_DAYS 日だけ見る。
    """
    token = cloud.access_token()
    params = {"maxResults": "100", "showDeleted": "true",
              "updatedMin": since or _default_since()}
    q = urllib.parse.urlencode(params)
    data = _get_json("calendar", f"{CALENDAR_API}/calendars/primary/events?{q}", token)
    rows = []
    for event in data.get("items") or []:
        updated = event.get("updated") or _EPOCH
        day = updated[:10]
        start = (event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date")
        summary = event.get("summary") or "(無題)"
        status = event.get("status") or "?"
        rows.append({
            "ts": updated,
            "uuid": f"calendar:{event['id']}@{day}",
            "text": f"{summary} / start={start or '?'} / status={status}",
            "meta": {"id": event["id"], "htmlLink": event.get("htmlLink")},
        })
    rows.sort(key=lambda r: (r["ts"], r["uuid"]))
    return rows


# ---- gdrive -------------------------------------------------------------------

def _drive_about_user() -> str:
    data = _get_json("gdrive", f"{DRIVE_API}/about?fields=user", cloud.access_token())
    user = data.get("user") or {}
    return user.get("emailAddress") or user.get("displayName") or "?"


def gdrive_verify() -> tuple[bool, str]:
    """必要スコープ drive.metadata.readonly の確認（無ければブラウザ承認）→ about.user の表示。"""
    return _ensure_scope_and_describe(GDRIVE_SCOPE, _drive_about_user)


def gdrive_read(since: str | None) -> list[dict]:
    """since 以降に更新されたファイルのメタデータを統一形式で modifiedTime 昇順に返す。

    files.list(q=modifiedTime > '<since>' and trashed=false, orderBy=modifiedTime, pageSize=100)
    の単発取得（ページングなし＝他アダプタと同じ前提）。中身は取らずメタデータだけ（正本は
    Drive のまま）。
    """
    token = cloud.access_token()
    since_q = (since or _default_since()).replace("Z", "")
    params = urllib.parse.urlencode({
        "q": f"modifiedTime > '{since_q}' and trashed = false",
        "orderBy": "modifiedTime",
        "pageSize": "100",
        "fields": "files(id,name,mimeType,modifiedTime,webViewLink)",
    })
    data = _get_json("gdrive", f"{DRIVE_API}/files?{params}", token)
    rows = []
    for f in data.get("files") or []:
        updated = f.get("modifiedTime") or _EPOCH
        day = updated[:10]
        rows.append({
            "ts": updated,
            "uuid": f"gdrive:{f['id']}@{day}",
            "text": f"{f.get('name')} / {f.get('mimeType')} / updated={updated}",
            "meta": {"id": f["id"], "webViewLink": f.get("webViewLink")},
        })
    rows.sort(key=lambda r: (r["ts"], r["uuid"]))
    return rows
