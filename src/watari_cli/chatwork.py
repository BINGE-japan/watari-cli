"""Chatwork connector（組み込み）。API トークン認証＋部屋メッセージの決定論リーダー。

REST API（https://api.chatwork.com/v2）に `X-ChatWorkToken: <token>` ヘッダで叩く。依存追加禁止の
ため HTTP は urllib のみ（transport 部分は connector_http.py に共通化して linear/github/notion と
同じ形にしている）。

- 疎通確認（`verify`）は `GET /me`。name（と organization_name があれば併記）を返す。
  watari connect のその場確認に使う。
- 読み取り（`read`）は `GET /rooms` で `last_update_time > since` の部屋を絞り込み、各部屋
  `GET /rooms/<id>/messages?force=1` を叩いて `send_time > since` のメッセージを統一形式
  {ts, uuid, text, meta} に整形する。
- スコープ制限: 1回の read で読む部屋数は最大 `MAX_ROOMS`（10）件。since 以降に更新された部屋が
  それを超える場合、超過分はその回では読まない（Chatwork には部屋一覧の時間範囲フィルタが無い
  ため、全部屋のメッセージを毎回叩くわけにはいかない）。運用上問題になったらページングを追加する。
- uuid は `chatwork:<room_id>:<message_id>`（SCHEMA.md の dedup 規約と同じ思想）。
- ts は Chatwork の epoch秒（send_time）を UTC ISO8601 に変換する。
- text は `[部屋名] 発言者: 本文先頭200字`。メッセージの中身は書き写さず、要点だけを畳む
  （正本は Chatwork のまま）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from watari_cli import connector_http
from watari_cli.connectors import ConnectorError

API_BASE = "https://api.chatwork.com/v2"

MAX_ROOMS = 10  # 1回の read で読む部屋数の上限（スコープ制限。docstring 参照）


def _http(method: str, url: str, headers: dict | None = None, data: bytes | None = None):
    """(status, body_bytes) を返す。linear.py と同じ薄いラッパー（テストが差し替える名前）。"""
    return connector_http.request("chatwork", method, url, headers, data)


def _headers(token: str) -> dict:
    return {"X-ChatWorkToken": token}


def _get(token: str, url: str):
    status, body = _http("GET", url, _headers(token))
    if status == 401:
        raise ConnectorError("chatwork: 認証エラー（API トークンを確認してください）")
    if status == 204:
        return []  # Chatwork は「新着メッセージなし」を 204 No Content で返す（正常系）
    if status != 200:
        raise ConnectorError(f"chatwork: API エラー({status}): {body[:200]!r}")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise ConnectorError(f"chatwork: 応答が JSON ではありません: {body[:200]!r}")


def verify(token: str) -> tuple[bool, str]:
    """疎通確認（GET /me）。成功時は (True, name（org名）)、失敗時は (False, 理由)。"""
    if not token:
        return False, "トークンが空です"
    try:
        data = _get(token, f"{API_BASE}/me")
    except ConnectorError as error:
        return False, str(error)
    name = data.get("name")
    if not name:
        return False, "name が取得できませんでした"
    org = data.get("organization_name")
    return True, f"{name}（{org}）" if org else name


def _epoch_to_iso(epoch) -> str:
    dt = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _iso_to_epoch(since: str | None) -> int:
    if not since:
        return 0
    return int(datetime.fromisoformat(since.replace("Z", "+00:00")).timestamp())


def read(token: str, since: str | None) -> list[dict]:
    """カーソル(since)以降に更新された部屋のメッセージを統一形式 [{ts,uuid,text,meta}, ...] で
    send_time 昇順に返す。

    since 省略時は全件（呼び出し側＝connectors.read が host カーソルを既定として渡す）。
    最大 MAX_ROOMS 部屋まで（docstring のスコープ制限参照）。
    """
    since_epoch = _iso_to_epoch(since)
    rooms = _get(token, f"{API_BASE}/rooms")
    candidates = [r for r in (rooms or []) if (r.get("last_update_time") or 0) > since_epoch]
    candidates = candidates[:MAX_ROOMS]

    rows = []
    for room in candidates:
        room_id = room["room_id"]
        room_name = room.get("name") or str(room_id)
        messages = _get(token, f"{API_BASE}/rooms/{room_id}/messages?force=1")
        if not isinstance(messages, list):
            continue  # 未読なし等でオブジェクトが返る場合がある
        for msg in messages:
            send_time = msg.get("send_time") or 0
            if send_time <= since_epoch:
                continue
            speaker = (msg.get("account") or {}).get("name") or "?"
            body = (msg.get("body") or "").strip().replace("\n", " ")
            rows.append({
                "ts": _epoch_to_iso(send_time),
                "uuid": f"chatwork:{room_id}:{msg['message_id']}",
                "text": f"[{room_name}] {speaker}: {body[:200]}",
                "meta": {"room_id": room_id, "message_id": msg["message_id"]},
            })
    rows.sort(key=lambda r: (r["ts"], r["uuid"]))
    return rows
