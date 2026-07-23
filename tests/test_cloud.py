"""クラウド置き場（Drive appDataFolder）アダプタの契約テスト。HTTP をモックしてオフライン検証。

実 Google エンドポイントは叩かない。ここでは REST の組み立て・パース・read-modify-write の
append・認可フラグ・incremental scope（authorize の loopback フロー自体は webbrowser.open だけ
差し替えてローカルで完結させ、実際にサーバへ到達させて固める）と、「同梱既定の OAuth
クライアントを置かない」こと（未設定時に案内経路へ落ちる）を検証する。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.parse

from watari_cli import cloud, config


class _Base(unittest.TestCase):
    # client_id/secret は config.json(google) から解決される（env で上書き可）。テストは XDG_CONFIG_HOME
    # を temp に隔離し、実環境の WATARI_GOOGLE_* env は消してから config に埋める。
    _ENV_KEYS = ("WATARI_GOOGLE_CLIENT_ID", "WATARI_GOOGLE_CLIENT_SECRET", "XDG_CONFIG_HOME")

    def setUp(self):
        self._cfg = tempfile.TemporaryDirectory(prefix="watari-cloud-")
        self._saved_env = {k: os.environ.get(k) for k in self._ENV_KEYS}
        os.environ.pop("WATARI_GOOGLE_CLIENT_ID", None)
        os.environ.pop("WATARI_GOOGLE_CLIENT_SECRET", None)
        os.environ["XDG_CONFIG_HOME"] = self._cfg.name
        # 同梱既定(_BUNDLED_*)が焼き込まれていてもテストは「未設定」を再現できるよう空に固定
        self._saved_bundled = (cloud._BUNDLED_CLIENT_ID, cloud._BUNDLED_CLIENT_SECRET)
        cloud._BUNDLED_CLIENT_ID = cloud._BUNDLED_CLIENT_SECRET = ""
        self._saved_http = cloud._http
        config.save_config(google={"client_id": "cid", "client_secret": "csec",
                                   "refresh_token": "RT"})
        self.calls: list = []

    def tearDown(self):
        cloud._BUNDLED_CLIENT_ID, cloud._BUNDLED_CLIENT_SECRET = self._saved_bundled
        cloud._http = self._saved_http
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._cfg.cleanup()

    def fake(self, router):
        def f(method, url, headers=None, data=None):
            self.calls.append((method, url, data))
            return router(method, url, data)
        cloud._http = f

    @staticmethod
    def _tok(url):
        return url == cloud._TOKEN_URL


class AuthTest(_Base):
    def test_flags_and_get_store(self):
        self.assertTrue(cloud.is_configured())
        self.assertTrue(cloud.is_authorized())
        self.assertIsInstance(cloud.get_store(), cloud.DriveAppDataStore)

    def test_unauthorized_get_store_none(self):
        config.save_config(google={})  # refresh token を消す
        self.assertFalse(cloud.is_authorized())
        self.assertIsNone(cloud.get_store())

    def test_unconfigured_is_not_authorized(self):
        config.save_config(google={"refresh_token": "RT"})  # client_id/secret を消す
        self.assertFalse(cloud.is_configured())
        self.assertFalse(cloud.is_authorized())

    def test_access_token_from_refresh(self):
        self.fake(lambda m, u, d: (200, b'{"access_token":"AT"}'))
        self.assertEqual(cloud._access_token(), "AT")
        self.assertEqual(self.calls[0][1], cloud._TOKEN_URL)

    def test_public_access_token_wrapper(self):
        self.fake(lambda m, u, d: (200, b'{"access_token":"AT2"}'))
        self.assertEqual(cloud.access_token(), "AT2")


class IncrementalScopeTest(_Base):
    """gmail/calendar/gdrive（google_connectors.py）が使う incremental scope の土台。"""

    def test_union_scopes_always_includes_drive_appdata_first(self):
        self.assertEqual(cloud._union_scopes(None), [cloud.SCOPE])
        self.assertEqual(cloud._union_scopes(["https://x/gmail.readonly"]),
                         [cloud.SCOPE, "https://x/gmail.readonly"])

    def test_union_scopes_dedupes_and_preserves_order(self):
        got = cloud._union_scopes([cloud.SCOPE, "a", "b", "a"])
        self.assertEqual(got, [cloud.SCOPE, "a", "b"])

    def test_granted_scopes_empty_when_unset(self):
        config.save_config(google={"refresh_token": "RT"})
        self.assertEqual(cloud.granted_scopes(), [])

    def test_granted_scopes_reads_config(self):
        config.save_config(google={"refresh_token": "RT", "scopes": [cloud.SCOPE, "extra"]})
        self.assertEqual(cloud.granted_scopes(), [cloud.SCOPE, "extra"])

    def test_authorize_full_loopback_flow_saves_granted_scopes(self):
        """実際に loopback サーバまで通す（webbrowser.open だけ差し替えて「ユーザーが承認した」を
        模す）。authorize(scopes) が要求スコープに追加スコープを含め、include_granted_scopes=true
        を付け、応答の scope 一覧をそのまま config.google.scopes に保存することを固める。"""
        import threading
        import urllib.request
        import webbrowser

        extra_scope = "https://www.googleapis.com/auth/gmail.readonly"
        seen_query: dict = {}

        def fake_open(url):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            seen_query.update(qs)
            redirect_uri = qs["redirect_uri"][0]
            callback = redirect_uri + "?" + urllib.parse.urlencode(
                {"code": "AUTHCODE", "state": qs["state"][0]})
            threading.Thread(
                target=lambda: urllib.request.urlopen(callback, timeout=5), daemon=True).start()
            return True

        def r(m, u, d):
            if u == cloud._TOKEN_URL:
                return 200, json.dumps({
                    "refresh_token": "NEWRT",
                    "scope": f"{cloud.SCOPE} {extra_scope}",
                }).encode()
            return 404, b"{}"
        self.fake(r)

        saved_open = webbrowser.open
        webbrowser.open = fake_open
        try:
            ok, message = cloud.authorize([extra_scope])
        finally:
            webbrowser.open = saved_open

        self.assertTrue(ok, message)
        self.assertIn(cloud.SCOPE, seen_query["scope"][0])
        self.assertIn(extra_scope, seen_query["scope"][0])
        self.assertEqual(seen_query["include_granted_scopes"][0], "true")
        self.assertEqual(config.load_config()["google"]["refresh_token"], "NEWRT")
        self.assertEqual(cloud.granted_scopes(), [cloud.SCOPE, extra_scope])


class AuthorizeFailureMessagesTest(_Base):
    """authorize の失敗メッセージがユーザー語＋再実行コマンド（watari auth）であること。
    OAuth 実装用語（state / refresh_token / token 交換）や bytes repr を出さない。"""

    def _authorize_with_callback(self, params: dict, token_response=(404, b"{}")):
        """loopback へ params のコールバックを送り、token エンドポイントは token_response を返す。"""
        import threading
        import urllib.request
        import webbrowser

        def fake_open(url):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            redirect_uri = qs["redirect_uri"][0]
            sent = dict(params)
            if sent.pop("_use_real_state", False):
                sent["state"] = qs["state"][0]
            callback = redirect_uri + "?" + urllib.parse.urlencode(sent)
            threading.Thread(
                target=lambda: urllib.request.urlopen(callback, timeout=5), daemon=True).start()
            return True

        self.fake(lambda m, u, d: token_response if u == cloud._TOKEN_URL else (404, b"{}"))
        saved_open = webbrowser.open
        webbrowser.open = fake_open
        try:
            return cloud.authorize()
        finally:
            webbrowser.open = saved_open

    def test_access_denied_is_translated_with_recovery_command(self):
        ok, message = self._authorize_with_callback({"error": "access_denied"})
        self.assertFalse(ok)
        self.assertIn("キャンセル", message)
        self.assertIn("watari auth", message)

    def test_state_mismatch_is_plain_language(self):
        ok, message = self._authorize_with_callback({"code": "AUTHCODE", "state": "WRONG"})
        self.assertFalse(ok)
        self.assertNotIn("state", message)
        self.assertIn("watari auth", message)

    def test_token_exchange_failure_has_no_bytes_repr(self):
        ok, message = self._authorize_with_callback(
            {"code": "AUTHCODE", "_use_real_state": True},
            token_response=(500, "サーバエラー".encode("utf-8")))
        self.assertFalse(ok)
        self.assertNotIn("b'", message)
        self.assertNotIn("token 交換", message)
        self.assertIn("watari auth", message)
        self.assertIn("サーバエラー", message)  # body は UTF-8 デコードして添える

    def test_missing_refresh_token_is_plain_language(self):
        ok, message = self._authorize_with_callback(
            {"code": "AUTHCODE", "_use_real_state": True},
            token_response=(200, b'{"access_token": "AT"}'))
        self.assertFalse(ok)
        self.assertNotIn("refresh_token", message)
        self.assertIn("watari auth", message)


class CredentialsTest(_Base):
    def test_resolve_from_config(self):
        self.assertEqual(cloud.credentials(), ("cid", "csec"))

    def test_env_overrides_config(self):
        os.environ["WATARI_GOOGLE_CLIENT_ID"] = "ENVID"
        os.environ["WATARI_GOOGLE_CLIENT_SECRET"] = "ENVSEC"
        self.assertEqual(cloud.credentials(), ("ENVID", "ENVSEC"))

    def test_save_credentials_persists_and_keeps_refresh_token(self):
        cloud.save_credentials("newid", "newsec")
        google = config.load_config()["google"]
        self.assertEqual((google["client_id"], google["client_secret"]), ("newid", "newsec"))
        self.assertEqual(google["refresh_token"], "RT")  # 既存の refresh_token は保持

    def test_bundled_default_used_when_config_empty(self):
        config.save_config(google={})
        self.assertEqual(cloud.credentials(), ("", ""))  # 既定は空（未配布）


class NoBundledCredentialsTest(unittest.TestCase):
    """同梱既定（_BUNDLED_*）は空であること（開発者個人の OAuth クライアントを配布物に
    焼き込まない——公開ブロッカー対応）と、未設定時に「未設定」経路へ落ちることを固める。

    _Base と違い _BUNDLED_* を差し替えない（ソースの実値そのものを検証する）。
    """

    _ENV_KEYS = ("WATARI_GOOGLE_CLIENT_ID", "WATARI_GOOGLE_CLIENT_SECRET", "XDG_CONFIG_HOME")

    def setUp(self):
        self._cfg = tempfile.TemporaryDirectory(prefix="watari-cloud-nobundle-")
        self._saved_env = {k: os.environ.get(k) for k in self._ENV_KEYS}
        os.environ.pop("WATARI_GOOGLE_CLIENT_ID", None)
        os.environ.pop("WATARI_GOOGLE_CLIENT_SECRET", None)
        os.environ["XDG_CONFIG_HOME"] = self._cfg.name

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._cfg.cleanup()

    def test_bundled_constants_are_empty(self):
        self.assertEqual(cloud._BUNDLED_CLIENT_ID, "")
        self.assertEqual(cloud._BUNDLED_CLIENT_SECRET, "")

    def test_unconfigured_without_env_or_config(self):
        self.assertEqual(cloud.credentials(), ("", ""))
        self.assertFalse(cloud.is_configured())
        self.assertFalse(cloud.is_authorized())
        self.assertIsNone(cloud.get_store())

    def test_authorize_falls_into_setup_guidance_when_unconfigured(self):
        ok, message = cloud.authorize()
        self.assertFalse(ok)
        self.assertIn("watari auth", message)  # 回復コマンドを必ず案内する
        self.assertNotIn("client_id", message)  # 英語フィールド名を出さない


class DriveOpsTest(_Base):
    def _store(self):
        return cloud.DriveAppDataStore()

    def test_list(self):
        def r(m, u, d):
            if self._tok(u):
                return 200, b'{"access_token":"AT"}'
            return 200, json.dumps({"files": [{"id": "1", "name": "a.jsonl"}]}).encode()
        self.fake(r)
        self.assertEqual(self._store().list()[0]["name"], "a.jsonl")

    def test_read(self):
        def r(m, u, d):
            if self._tok(u):
                return 200, b'{"access_token":"AT"}'
            if "&q=" in u:
                return 200, json.dumps({"files": [{"id": "F", "name": "m.jsonl"}]}).encode()
            if "alt=media" in u:
                return 200, "hello\n".encode()
            return 404, b"{}"
        self.fake(r)
        self.assertEqual(self._store().read("m.jsonl"), "hello\n")

    def test_read_missing_returns_empty(self):
        def r(m, u, d):
            if self._tok(u):
                return 200, b'{"access_token":"AT"}'
            return 200, b'{"files":[]}'
        self.fake(r)
        self.assertEqual(self._store().read("nope.jsonl"), "")

    def test_write_create_uses_multipart_post(self):
        def r(m, u, d):
            if self._tok(u):
                return 200, b'{"access_token":"AT"}'
            if "&q=" in u:
                return 200, b'{"files":[]}'
            if "uploadType=multipart" in u:
                return 200, b'{"id":"NEW"}'
            return 404, b"{}"
        self.fake(r)
        self._store().write("m.jsonl", "x\n")
        self.assertTrue(any(c[0] == "POST" and "uploadType=multipart" in c[1] for c in self.calls))

    def test_write_update_uses_patch_media(self):
        def r(m, u, d):
            if self._tok(u):
                return 200, b'{"access_token":"AT"}'
            if "&q=" in u:
                return 200, json.dumps({"files": [{"id": "F", "name": "m.jsonl"}]}).encode()
            if "uploadType=media" in u:
                return 200, b'{"id":"F"}'
            return 404, b"{}"
        self.fake(r)
        self._store().write("m.jsonl", "y\n")
        self.assertTrue(any(c[0] == "PATCH" and "uploadType=media" in c[1] for c in self.calls))

    def test_append_is_read_modify_write(self):
        state = {"content": "old\n"}

        def r(m, u, d):
            if self._tok(u):
                return 200, b'{"access_token":"AT"}'
            if "&q=" in u:
                return 200, json.dumps({"files": [{"id": "F", "name": "m.jsonl"}]}).encode()
            if "alt=media" in u:
                return 200, state["content"].encode()
            if "uploadType=media" in u:
                state["content"] = d.decode()
                return 200, b'{"id":"F"}'
            return 404, b"{}"
        self.fake(r)
        self._store().append("m.jsonl", "new\n")
        self.assertEqual(state["content"], "old\nnew\n")

    def test_delete(self):
        def r(m, u, d):
            if self._tok(u):
                return 200, b'{"access_token":"AT"}'
            if "&q=" in u:
                return 200, json.dumps({"files": [{"id": "F", "name": "m.jsonl"}]}).encode()
            if m == "DELETE":
                return 204, b""
            return 404, b"{}"
        self.fake(r)
        self._store().delete("m.jsonl")
        self.assertTrue(any(c[0] == "DELETE" for c in self.calls))


if __name__ == "__main__":
    unittest.main()
