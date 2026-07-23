"""urllib ベースの HTTP 送受信を一箇所に集約する（linear/github/notion の三重複を避ける）。

サービス固有の意味づけ（ステータスコード→エラーメッセージ、応答 JSON の中身の検査、
GraphQL か REST かの違い）は各アダプタ（linear.py/github.py/notion.py）側の責務のまま。
ここは transport 層（「リクエストを送って (status, body_bytes) を返す。ネットワーク断は
ConnectorError」）と、ユーザー向けエラー表示の共通部品（body_text / reconnect_hint）だけを
共通化する。依存追加禁止のため urllib のみ。
"""
from __future__ import annotations

import urllib.error
import urllib.request

from watari_cli.connectors import ConnectorError


def request(service: str, method: str, url: str, headers: dict | None = None,
            data: bytes | None = None) -> tuple[int, bytes]:
    """(status, body_bytes) を返す。HTTP エラーは (code, body)、ネットワーク断は ConnectorError。"""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        raise ConnectorError(
            f"{service}: ネットワークに接続できませんでした。通信環境を確認して、"
            f"もう一度実行してください（詳細: {e}）")


def body_text(body: bytes | str, limit: int = 200) -> str:
    """API 応答 body をユーザー向け表示用に整える（UTF-8 デコード・空白を畳んで limit 文字まで）。

    bytes の repr（b'...'）をそのままユーザーに見せないための共通ヘルパー。
    全サービス（linear/github/notion/slack/chatwork/freee/google/cloud）がこれを使う。
    """
    if isinstance(body, (bytes, bytearray)):
        text = bytes(body).decode("utf-8", "replace")
    else:
        text = str(body)
    return " ".join(text.split())[:limit]


def reconnect_hint(service: str) -> str:
    """失敗時に必ず添える「次の一歩」の定型文（全サービス共通の言い回し）。"""
    return f"もう一度接続するには: watari connect {service}"
