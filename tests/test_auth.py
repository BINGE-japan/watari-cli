"""`watari auth`（単独 Google 認証）と install の承認統一の契約テスト。

実 OAuth/実ブラウザは叩かず、cloud.authorize と対話プロンプトをモックして経路だけ固める:
- creds が config にあれば入力を求めず authorize に進む。
- creds が無ければ対話入力→config 保存→authorize（env 由来でも config に焼く）。
- install の承認ブロックは watari auth と同じ _google_auth_flow(prompt_for_creds=False) を通る。
"""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest

from watari_cli import cli, cloud, config, prompts
from watari_cli.cli import _build_parser


def _run(argv):
    args = _build_parser().parse_args(argv)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = args.func(args)
    return rc, out.getvalue(), err.getvalue()


class _Base(unittest.TestCase):
    _ENV_KEYS = ("WATARI_GOOGLE_CLIENT_ID", "WATARI_GOOGLE_CLIENT_SECRET", "XDG_CONFIG_HOME")

    def setUp(self):
        self._cfg = tempfile.TemporaryDirectory(prefix="watari-auth-")
        self._saved_env = {k: os.environ.get(k) for k in self._ENV_KEYS}
        os.environ.pop("WATARI_GOOGLE_CLIENT_ID", None)
        os.environ.pop("WATARI_GOOGLE_CLIENT_SECRET", None)
        os.environ["XDG_CONFIG_HOME"] = self._cfg.name
        # 同梱既定(_BUNDLED_*)が焼き込まれていてもテストは「未設定」を再現できるよう空に固定
        self._saved_bundled = (cloud._BUNDLED_CLIENT_ID, cloud._BUNDLED_CLIENT_SECRET)
        cloud._BUNDLED_CLIENT_ID = cloud._BUNDLED_CLIENT_SECRET = ""
        self._saved = {"authorize": cloud.authorize, "http": cloud._http,
                       "text": prompts.text, "confirm": prompts.confirm}
        self.authorized_with = []
        cloud.authorize = lambda: (self.authorized_with.append(cloud.credentials()) or (True, "ok"))

    def tearDown(self):
        cloud._BUNDLED_CLIENT_ID, cloud._BUNDLED_CLIENT_SECRET = self._saved_bundled
        cloud.authorize = self._saved["authorize"]
        cloud._http = self._saved["http"]
        prompts.text = self._saved["text"]
        prompts.confirm = self._saved["confirm"]
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._cfg.cleanup()


class AuthCommandTest(_Base):
    def test_uses_saved_creds_without_prompting(self):
        config.save_config(google={"client_id": "cid", "client_secret": "csec"})
        prompts.text = lambda *a, **k: self.fail("入力を求めてはいけない")
        rc, out, _ = _run(["auth"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.authorized_with, [("cid", "csec")])  # 保存値で承認

    def test_prompts_for_creds_then_saves_and_authorizes(self):
        answers = iter(["typedid", "typedsec"])
        prompts.text = lambda *a, **k: next(answers)
        rc, out, _ = _run(["auth"])
        self.assertEqual(rc, 0)
        google = config.load_config()["google"]
        self.assertEqual((google["client_id"], google["client_secret"]), ("typedid", "typedsec"))
        self.assertEqual(self.authorized_with, [("typedid", "typedsec")])

    def test_env_creds_are_persisted_to_config(self):
        os.environ["WATARI_GOOGLE_CLIENT_ID"] = "envid"
        os.environ["WATARI_GOOGLE_CLIENT_SECRET"] = "envsec"
        prompts.text = lambda *a, **k: self.fail("env があるので入力を求めない")
        rc, _, _ = _run(["auth"])
        self.assertEqual(rc, 0)
        google = config.load_config()["google"]
        self.assertEqual((google["client_id"], google["client_secret"]), ("envid", "envsec"))

    def test_empty_input_aborts(self):
        prompts.text = lambda *a, **k: ""
        rc, out, _ = _run(["auth"])
        self.assertEqual(rc, 1)
        self.assertEqual(self.authorized_with, [])  # 承認まで行かない

    def test_deleted_saved_client_prompts_for_replacement(self):
        config.save_config(google={
            "client_id": "deleted-id", "client_secret": "deleted-secret",
            "refresh_token": "stale-token", "scopes": [cloud.SCOPE],
        })
        cloud._http = lambda *args, **kwargs: (
            401, b'{"error":"deleted_client","error_description":"The OAuth client was deleted."}')
        answers = iter(["new-id", "new-secret"])
        prompts.text = lambda *a, **k: next(answers)

        rc, out, _ = _run(["auth"])

        self.assertEqual(rc, 0)
        self.assertIn("削除されています", out)
        google = config.load_config()["google"]
        self.assertEqual((google["client_id"], google["client_secret"]),
                         ("new-id", "new-secret"))
        self.assertNotIn("refresh_token", google)
        self.assertNotIn("scopes", google)
        self.assertEqual(self.authorized_with, [("new-id", "new-secret")])

    def test_revoked_token_keeps_existing_client_for_reauthorization(self):
        config.save_config(google={
            "client_id": "current-id", "client_secret": "current-secret",
            "refresh_token": "revoked-token", "scopes": [cloud.SCOPE],
        })
        cloud._http = lambda *args, **kwargs: (
            400, b'{"error":"invalid_grant","error_description":"Token revoked"}')
        prompts.text = lambda *a, **k: self.fail("clientが有効なら差し替え入力を求めてはいけない")

        rc, _out, _ = _run(["auth"])

        self.assertEqual(rc, 0)
        self.assertEqual(self.authorized_with, [("current-id", "current-secret")])


class InstallUnifiesAuthTest(_Base):
    def test_install_authorizes_via_shared_flow_without_creds_prompt(self):
        # creds を config に用意（is_configured=True・未認証）。install の承認 yes で共有経路を通る。
        config.save_config(google={"client_id": "cid", "client_secret": "csec"})
        prompts.confirm = lambda *a, **k: True
        prompts.text = lambda *a, **k: self.fail("install では creds 入力を求めない")
        home = os.path.join(self._cfg.name, "mem")
        rc, out, _ = _run(["install", "--home", home])
        self.assertEqual(rc, 0)
        self.assertEqual(self.authorized_with, [("cid", "csec")])

    def test_install_skips_auth_when_unconfigured(self):
        # creds 未設定なら install は承認を促さない（fresh 体験を汚さない。後で watari auth）。
        prompts.confirm = lambda *a, **k: self.fail("未設定なら同期を尋ねない")
        home = os.path.join(self._cfg.name, "mem2")
        rc, _, _ = _run(["install", "--home", home])
        self.assertEqual(rc, 0)
        self.assertEqual(self.authorized_with, [])


if __name__ == "__main__":
    unittest.main()
