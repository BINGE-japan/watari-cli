"""マシン間の発話中継所（クラウド置き場）。第一実装 = Google Drive appDataFolder。

なぜクラウドで、なぜ git でないか: 生の発話素材は「消せる・機械可読・無人で読める」置き場が要る。
git は履歴から blob を消せず容量が単調増加するため素材置き場に不適（カセット git は蒸留済み記憶専用）。
appDataFolder はユーザーの Drive UI に出ず、アプリ専用で、API で削除できる。

依存を増やさないため HTTP は標準ライブラリ(urllib)だけで叩く。バックエンドは `CloudStore` で
抽象化し、今は Drive appDataFolder を第一実装とする（将来の差し替え余地。他実装は今は作らない）。

認証 = Google OAuth（インストール型アプリ・loopback フロー）。client_id/secret は watari-cli 同梱
（インストール型では secret は機密でない）。未登録の間は空——登録手順は docs/google-oauth-setup.md。
リフレッシュトークンはユーザー設定(config.json)に保存する。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid

from watari_cli import config

SCOPE = "https://www.googleapis.com/auth/drive.appdata"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

# binge が登録した OAuth アプリの client_id/secret を同梱する。未登録の間は空。
# docs/google-oauth-setup.md の手順で埋める（環境変数でも上書き可）。
_CLIENT_ID = os.environ.get("WATARI_GOOGLE_CLIENT_ID", "")
_CLIENT_SECRET = os.environ.get("WATARI_GOOGLE_CLIENT_SECRET", "")


class CloudError(Exception):
    """クラウド置き場の操作失敗（呼び出し側はスキップ/繰り越しで扱う）。"""


def _http(method: str, url: str, headers: dict | None = None, data: bytes | None = None):
    """(status, body_bytes) を返す。HTTP エラーは (code, body)、ネットワーク断は CloudError。"""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        raise CloudError(f"network error: {e}")


def is_configured() -> bool:
    """OAuth アプリ（client_id/secret）が同梱/設定されているか。"""
    return bool(_CLIENT_ID and _CLIENT_SECRET)


def _refresh_token() -> str | None:
    return (config.load_config().get("google") or {}).get("refresh_token")


def is_authorized() -> bool:
    return is_configured() and bool(_refresh_token())


def _access_token() -> str:
    rt = _refresh_token()
    if not rt:
        raise CloudError("Google 未認証（watari install で承認、または docs/google-oauth-setup.md）")
    data = urllib.parse.urlencode({
        "client_id": _CLIENT_ID, "client_secret": _CLIENT_SECRET,
        "refresh_token": rt, "grant_type": "refresh_token",
    }).encode()
    status, body = _http("POST", _TOKEN_URL,
                         {"Content-Type": "application/x-www-form-urlencoded"}, data)
    if status != 200:
        raise CloudError(f"token refresh 失敗({status}): {body[:200]!r}")
    return json.loads(body)["access_token"]


class CloudStore:
    """発話中継所の抽象。名前付き JSONL ファイル群を list/read/append/write/delete する。"""

    def list(self) -> list[dict]:  # [{name, id, size, modifiedTime}, ...]
        raise NotImplementedError

    def read(self, name: str) -> str:
        raise NotImplementedError

    def append(self, name: str, text: str) -> None:
        raise NotImplementedError

    def write(self, name: str, text: str) -> None:
        raise NotImplementedError

    def delete(self, name: str) -> None:
        raise NotImplementedError


class DriveAppDataStore(CloudStore):
    """Google Drive appDataFolder 実装（Drive REST v3・urllib）。"""

    API = "https://www.googleapis.com/drive/v3"
    UPLOAD = "https://www.googleapis.com/upload/drive/v3"

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"Authorization": f"Bearer {_access_token()}"}
        if extra:
            h.update(extra)
        return h

    def _find(self, name: str) -> dict | None:
        q = urllib.parse.quote(f"name='{name}'")
        url = (f"{self.API}/files?spaces=appDataFolder&q={q}"
               "&fields=files(id,name,size,modifiedTime)")
        status, body = _http("GET", url, self._headers())
        if status != 200:
            raise CloudError(f"find 失敗({status}): {body[:200]!r}")
        files = json.loads(body).get("files", [])
        return files[0] if files else None

    def list(self) -> list[dict]:
        url = (f"{self.API}/files?spaces=appDataFolder"
               "&fields=files(id,name,size,modifiedTime)&pageSize=1000")
        status, body = _http("GET", url, self._headers())
        if status != 200:
            raise CloudError(f"list 失敗({status}): {body[:200]!r}")
        return json.loads(body).get("files", [])

    def read(self, name: str) -> str:
        f = self._find(name)
        if not f:
            return ""
        status, body = _http("GET", f"{self.API}/files/{f['id']}?alt=media", self._headers())
        if status not in (200, 206):
            raise CloudError(f"read 失敗({status}): {body[:200]!r}")
        return body.decode("utf-8")

    def write(self, name: str, text: str) -> None:
        f = self._find(name)
        data = text.encode("utf-8")
        if f:
            url = f"{self.UPLOAD}/files/{f['id']}?uploadType=media"
            status, body = _http("PATCH", url,
                                 self._headers({"Content-Type": "text/plain"}), data)
        else:
            boundary = "watari-" + uuid.uuid4().hex
            meta = json.dumps({"name": name, "parents": ["appDataFolder"]})
            payload = (
                f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
                f"--{boundary}\r\nContent-Type: text/plain\r\n\r\n"
            ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
            url = f"{self.UPLOAD}/files?uploadType=multipart"
            status, body = _http("POST", url,
                self._headers({"Content-Type": f"multipart/related; boundary={boundary}"}), payload)
        if status not in (200, 201):
            raise CloudError(f"write 失敗({status}): {body[:200]!r}")

    def append(self, name: str, text: str) -> None:
        # appDataFolder は真の追記が無いので read-modify-write。ファイルは machine ごと単一書き手
        # ＋消化済みは削除されて小さいまま保たれるので、全文往復でも実用上問題ない。
        self.write(name, self.read(name) + text)

    def delete(self, name: str) -> None:
        f = self._find(name)
        if not f:
            return
        status, body = _http("DELETE", f"{self.API}/files/{f['id']}", self._headers())
        if status not in (200, 204):
            raise CloudError(f"delete 失敗({status}): {body[:200]!r}")


def get_store() -> CloudStore | None:
    """認証済みなら Drive 実装、未設定/未認証なら None（呼び出し側は同期をスキップ）。"""
    if not is_authorized():
        return None
    return DriveAppDataStore()


def authorize() -> tuple[bool, str]:
    """インストール型 OAuth（loopback）。ブラウザで承認 → refresh token を config に保存。(ok, メッセージ)。

    ブラウザが無い/開けない環境向けに URL は標準出力にも出す。既に承認済みなら再承認して更新。
    """
    if not is_configured():
        return False, "Google の client_id/secret 未設定（docs/google-oauth-setup.md 参照）"
    import http.server
    import secrets
    import threading
    import time
    import webbrowser

    captured: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in params or "error" in params:
                captured["code"] = params.get("code", [None])[0]
                captured["state"] = params.get("state", [None])[0]
                captured["error"] = params.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("認証を受け取りました。ターミナルに戻ってください。".encode("utf-8"))

        def log_message(self, *a):  # 静かに
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}"
    state = secrets.token_urlsafe(16)
    auth_url = _AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": _CLIENT_ID, "redirect_uri": redirect_uri, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": state,
    })
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("ブラウザで Google 認証を開きます。開かなければ次の URL を貼ってください:")
    print(f"  {auth_url}")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass
    for _ in range(600):  # 最長 5 分待つ
        if captured:
            break
        time.sleep(0.5)
    server.shutdown()
    server.server_close()

    if captured.get("error") or not captured.get("code"):
        return False, f"認証されませんでした（{captured.get('error') or 'timeout'}）"
    if captured.get("state") != state:
        return False, "state 不一致（認証を中断しました）"
    data = urllib.parse.urlencode({
        "code": captured["code"], "client_id": _CLIENT_ID, "client_secret": _CLIENT_SECRET,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code",
    }).encode()
    status, body = _http("POST", _TOKEN_URL,
                         {"Content-Type": "application/x-www-form-urlencoded"}, data)
    if status != 200:
        return False, f"token 交換失敗({status}): {body[:200]!r}"
    rt = json.loads(body).get("refresh_token")
    if not rt:
        return False, "refresh_token が返りませんでした（同意画面で offline アクセスの許可が必要）"
    google = config.load_config().get("google") or {}
    google["refresh_token"] = rt
    config.save_config(google=google)
    return True, "Google 認証を保存しました"
