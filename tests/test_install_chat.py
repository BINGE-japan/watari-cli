"""install wizard の provider/Pi 選択 と watari chat の provider/model 自動注入の契約テスト。

install は provider/model（非秘密）だけを config に保存し、API キーは保存しない
（env か Pi の /login に委ねる）。chat は保存値を自動で Pi コマンドへ載せ、フラグは上書き。
ユーザーが生フラグを手組みしないための配線を固める。

注: config は XDG_CONFIG_HOME 配下に載るので一時ディレクトリへ隔離する。cmd_chat は home の
存在チェックだけなので、他 engine テストと同様に wl.MEM を一時ディレクトリへ直接差し替える。
"""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest

from watari_cli import config
from watari_cli.cli import _build_parser, _install_wizard, _provider_env_present
from watari_cli.engine import watari_lib as wl


def _run(argv):
    args = _build_parser().parse_args(argv)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = args.func(args)
    return rc, out.getvalue(), err.getvalue()


class _XdgIsolated(unittest.TestCase):
    def setUp(self):
        self._cfg = tempfile.TemporaryDirectory(prefix="watari-ic-cfg-")
        self._saved_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._cfg.name

    def tearDown(self):
        if self._saved_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._saved_xdg
        self._cfg.cleanup()


class WizardPlanTest(_XdgIsolated):
    """フラグ駆動（非対話）の plan。副作用なし（wizard は決定だけ）。"""

    def _plan(self, argv):
        return _install_wizard(_build_parser().parse_args(argv))

    def test_provider_flag_with_yes_is_noninteractive(self):
        plan = self._plan(["install", "--yes", "--provider", "anthropic"])
        self.assertEqual(plan["provider"], "anthropic")
        self.assertIsNone(plan["model"])
        self.assertFalse(plan["install_pi"])  # --yes は非対話＝Pi 導入を勝手に決めない

    def test_home_flag_is_noninteractive_and_does_not_ask_provider(self):
        plan = self._plan(["install", "--home", "/tmp/watari-nowhere-xyz", "--model", "m1"])
        self.assertIsNone(plan["provider"])  # 非対話では menu を出さない（勝手に選ばない）
        self.assertEqual(plan["model"], "m1")
        self.assertFalse(plan["install_pi"])


class InstallDryRunTest(_XdgIsolated):
    """--dry-run は副作用ゼロ（config を書かない）で、provider/Pi の予定を見せる。"""

    def test_shows_provider_and_pi_and_saves_nothing(self):
        rc, out, _ = _run(["install", "--dry-run", "--yes", "--provider", "anthropic"])
        self.assertEqual(rc, 0)
        self.assertIn("AI プロバイダ: anthropic", out)
        self.assertIn("Pi 導入:", out)
        self.assertIn("AI: anthropic", out)      # 完了表示のプレビューにも出る
        self.assertEqual(config.load_config(), {})  # dry-run は何も保存しない

    def test_without_provider_shows_unset(self):
        rc, out, _ = _run(["install", "--dry-run", "--yes"])
        self.assertEqual(rc, 0)
        self.assertIn("未指定", out)
        self.assertEqual(config.load_config(), {})


class ChatInjectionTest(_XdgIsolated):
    """watari chat が保存済み provider/model を自動で Pi コマンドへ載せる（フラグは上書き）。"""

    def setUp(self):
        super().setUp()
        self._saved_mem = wl.MEM
        self._home = tempfile.TemporaryDirectory(prefix="watari-ic-home-")
        wl.MEM = self._home.name  # chat は home の存在チェックだけ

    def tearDown(self):
        wl.MEM = self._saved_mem
        self._home.cleanup()
        super().tearDown()

    def test_saved_provider_model_are_injected(self):
        config.save_config(provider="anthropic", model="claude-x")
        rc, out, _ = _run(["chat", "--show"])
        self.assertEqual(rc, 0)
        self.assertIn("--provider anthropic", out)
        self.assertIn("--model claude-x", out)

    def test_flag_overrides_saved_provider(self):
        config.save_config(provider="google")
        rc, out, _ = _run(["chat", "--show", "--provider", "anthropic"])
        self.assertEqual(rc, 0)
        self.assertIn("--provider anthropic", out)
        self.assertNotIn("google", out)

    def test_no_provider_means_no_flag(self):
        rc, out, _ = _run(["chat", "--show"])
        self.assertEqual(rc, 0)
        self.assertNotIn("--provider", out)


class ProviderEnvTest(_XdgIsolated):
    def test_present_and_absent(self):
        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            os.environ["ANTHROPIC_API_KEY"] = "x"
            self.assertTrue(_provider_env_present("anthropic"))
            del os.environ["ANTHROPIC_API_KEY"]
            self.assertFalse(_provider_env_present("anthropic"))
            self.assertFalse(_provider_env_present("unknown-provider"))
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved


if __name__ == "__main__":
    unittest.main()
