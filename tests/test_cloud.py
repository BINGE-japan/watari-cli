"""クラウド置き場（Drive appDataFolder）アダプタの契約テスト。HTTP をモックしてオフライン検証。

実 OAuth/実 Drive は binge のアプリ登録が要るのでここでは検証しない（docs/google-oauth-setup.md）。
ここでは REST の組み立て・パース・read-modify-write の append・認可フラグを固める。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

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
