"""urllib ベースの HTTP 送受信を一箇所に集約する（linear/github/notion の三重複を避ける）。

サービス固有の意味づけ（ステータスコード→エラーメッセージ、応答 JSON の中身の検査、
GraphQL か REST かの違い）は各アダプタ（linear.py/github.py/notion.py）側の責務のまま。
ここは「リクエストを送って (status, body_bytes) を返す。ネットワーク断は ConnectorError」
という transport 層だけを共通化する。依存追加禁止のため urllib のみ。
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
        raise ConnectorError(f"{service}: ネットワークエラー: {e}")
