"""install ウィザードの UX 契約テスト（§4: 再実行導線・同期の既定・URL 空 Enter の明示）。

_install_wizard は副作用ゼロで plan(dict) を返すコンポーネントなので、prompts を
モックして選択の流れだけ固める。実行系（_prepare_memory）はエラー文言の契約のみ確認する。
"""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest

from watari_cli import cli, prompts
from watari_cli.cli import _build_parser


def _wizard(argv, select=None, text=None):
    """install の argv で _install_wizard だけを回す。(plan, stdout) を返す。"""
    args = _build_parser().parse_args(["install"] + argv)
    saved = (prompts.select, prompts.text)
    if select is not None:
        prompts.select = select
    if text is not None:
        prompts.text = text
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            plan = cli._install_wizard(args)
    finally:
        prompts.select, prompts.text = saved
    return plan, out.getvalue()


class InstallRerunTest(unittest.TestCase):
    """既定保存先に記憶があるとき、先頭・既定が「今ある記憶をそのまま使う」になる。"""

    def setUp(self):
        self._data = tempfile.TemporaryDirectory(prefix="watari-inst-data-")
        self._saved_xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = self._data.name
        self.default_dir = os.path.join(self._data.name, "watari", "memory")

    def tearDown(self):
        if self._saved_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self._saved_xdg
        self._data.cleanup()

    def test_existing_memory_offers_adopt_default_first(self):
        os.makedirs(os.path.join(self.default_dir, "life"), exist_ok=True)
        captured = {}

        def fake_select(message, options, default=0):
            captured.setdefault("options", []).append(options)
            return options[default][1]  # 既定をそのまま選ぶ

        plan, _out = _wizard([], select=fake_select)
        first_label, first_value = captured["options"][0][0]
        self.assertIn("今ある記憶をそのまま使う", first_label)
        self.assertIn(self.default_dir, first_label)
        # 既定選択の結果は adopt（記憶を消さない）で、保存先は既定ディレクトリ
        self.assertEqual(plan["mode"], "adopt")
        self.assertEqual(plan["home"], self.default_dir)

    def test_fresh_machine_offers_new_first(self):
        captured = {}

        def fake_select(message, options, default=0):
            captured.setdefault("options", []).append(options)
            return options[default][1]

        plan, _out = _wizard([], select=fake_select)
        self.assertEqual(captured["options"][0][0][0], "新しく始める")
        self.assertEqual(plan["mode"], "new")


class InstallSyncQuestionTest(unittest.TestCase):
    """同期の既定は「このパソコンだけで使う」。URL 空 Enter は明示メッセージ付きで同期なしへ。"""

    def setUp(self):
        self._data = tempfile.TemporaryDirectory(prefix="watari-inst-sync-")
        self._saved_xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = self._data.name

    def tearDown(self):
        if self._saved_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self._saved_xdg
        self._data.cleanup()

    def test_sync_default_is_local_only(self):
        captured = {}

        def fake_select(message, options, default=0):
            captured[message] = (options, default)
            return options[default][1]

        plan, _out = _wizard([], select=fake_select)
        sync_q = next(m for m in captured if "共有・バックアップ" in m)
        options, default = captured[sync_q]
        self.assertIn("このパソコンだけで使う", options[default][0])  # 既定=ローカル
        self.assertIsNone(plan["git_remote"])

    def test_empty_url_falls_back_with_explicit_message(self):
        def fake_select(message, options, default=0):
            if "共有・バックアップ" in message:
                return "remote"  # 「git リポジトリと同期する」を選ぶ
            return options[default][1]

        plan, out = _wizard([], select=fake_select, text=lambda *a, **k: "")
        self.assertIsNone(plan["git_remote"])
        # 黙って同期なしに落とさない（明示メッセージと再設定方法を出す）
        self.assertIn("URL が入力されなかったため、同期なしで続けます", out)
        self.assertIn("watari install --remote", out)

    def test_url_prompt_shows_example(self):
        captured = {}

        def fake_select(message, options, default=0):
            if "共有・バックアップ" in message:
                return "remote"
            return options[default][1]

        def fake_text(message, default=None):
            captured["prompt"] = message
            return "git@github.com:me/watari-memory.git"

        plan, out = _wizard([], select=fake_select, text=fake_text)
        self.assertIn("例: git@github.com:", captured["prompt"])
        self.assertIn("空のプライベートリポジトリ", out)  # 事前準備の一行案内
        self.assertEqual(plan["git_remote"], "git@github.com:me/watari-memory.git")


class PrepareMemoryErrorTest(unittest.TestCase):
    """new モードで既存記憶に当たったときのエラーが「引き継ぐ」導線を案内する。"""

    def test_new_on_existing_memory_points_to_adopt(self):
        with tempfile.TemporaryDirectory(prefix="watari-inst-prep-") as home:
            open(os.path.join(home, "something"), "w").close()
            with self.assertRaises(RuntimeError) as cm:
                cli._prepare_memory("new", home, None)
            message = str(cm.exception)
            self.assertIn("既にワタリの記憶があります", message)
            self.assertIn("このパソコンにある記憶フォルダを使う", message)


if __name__ == "__main__":
    unittest.main()
