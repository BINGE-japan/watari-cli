"""トップ --help / 日本語エラー / scan 改名 / 未セットアップ統一文言の契約テスト。

- watari --help は自前整形（はじめかた／よく使うコマンド／内部コマンドの3節）。
- 打ち間違いは difflib で候補を出す日本語エラー（「もしかして: status ?」）。
- `watari scan` が正式名、`watari dream` は隠し alias（同じ cmd_scan に落ちる。help には出ない）。
- 未セットアップ時は status/host/recall/audit/regen/scan/chat の全部が同一文言・exit 1・
  traceback なし（MSG_SETUP_REQUIRED）。
- chat --show は同梱スラッシュコマンド（skill/prompts/*.md）を --prompt-template で列挙する。
"""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest

from watari_cli.cli import _build_parser, cmd_scan
from watari_cli.engine import watari_lib as wl


def _run(argv):
    args = _build_parser().parse_args(argv)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = args.func(args)
    return rc, out.getvalue(), err.getvalue()


class TopHelpTest(unittest.TestCase):
    def test_top_help_has_three_sections(self):
        text = _build_parser().format_help()
        self.assertIn("はじめかた:", text)
        self.assertIn("よく使うコマンド:", text)
        self.assertIn("内部コマンド（ワタリが自動で使います。手で打つ必要はありません）:", text)
        self.assertIn("watari install", text)
        self.assertIn("watari chat", text)

    def test_top_help_hides_dream_and_shows_scan(self):
        text = _build_parser().format_help()
        self.assertIn("scan", text)
        self.assertNotIn("dream", text)

    def test_subcommands_have_description(self):
        # 各サブコマンドの --help に1〜3行の説明が出る（description= が付いている）
        parser = _build_parser()
        actions = [a for a in parser._actions
                   if isinstance(a, type(parser._subparsers._group_actions[0]))]
        sub = parser._subparsers._group_actions[0]
        for name, sp in sub.choices.items():
            with self.subTest(command=name):
                self.assertTrue(sp.description, f"description が無い: {name}")


class JapaneseErrorTest(unittest.TestCase):
    def _error_output(self, argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as cm:
                _build_parser().parse_args(argv)
        return cm.exception.code, err.getvalue()

    def test_typo_suggests_close_match(self):
        code, err = self._error_output(["stauts"])
        self.assertEqual(code, 2)
        self.assertIn("'stauts' は不明なコマンドです", err)
        self.assertIn("もしかして", err)
        self.assertIn("status", err)
        self.assertNotIn("invalid choice", err)  # 英語の定型文を出さない

    def test_suggestions_do_not_leak_hidden_dream_alias(self):
        _code, err = self._error_output(["dreem"])
        self.assertNotIn("dream", err)  # 隠し alias は候補に出さない（scan を出す）


class ScanRenameTest(unittest.TestCase):
    def test_scan_is_canonical_and_dream_is_alias(self):
        for name in ("scan", "dream"):
            with self.subTest(command=name):
                args = _build_parser().parse_args([name])
                self.assertIs(args.func, cmd_scan)


class SetupRequiredUnifiedTest(unittest.TestCase):
    """記憶フォルダ不在時、どのコマンドから入っても同じ文言・exit 1 で watari install を案内。"""

    def setUp(self):
        self._saved_mem = wl.MEM
        wl.MEM = "/nonexistent/watari-test-home"

    def tearDown(self):
        wl.MEM = self._saved_mem

    def test_all_commands_use_same_message(self):
        for argv in (["status"], ["host"], ["recall"], ["scan"], ["chat", "--show"]):
            with self.subTest(argv=argv):
                rc, out, err = _run(argv)
                self.assertEqual(rc, 1)
                self.assertIn("まだセットアップされていません", err)
                self.assertIn("watari install", err)

    def test_recall_does_not_emit_null_json(self):
        rc, out, _err = _run(["recall"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")  # life/learning とも null の JSON を出さない

    def test_audit_and_regen_catch_engine_file_not_found(self):
        # ディレクトリはあるが log.jsonl が無い＝engine が FileNotFoundError を投げる状態
        with tempfile.TemporaryDirectory(prefix="watari-help-noinit-") as home:
            wl.MEM = home
            for argv in (["audit"], ["regen"]):
                with self.subTest(argv=argv):
                    rc, _out, err = _run(argv)
                    self.assertEqual(rc, 1)
                    self.assertIn("まだセットアップされていません", err)
                    self.assertNotIn("Traceback", err)


class ChatShowPromptTemplatesTest(unittest.TestCase):
    def setUp(self):
        self._cfg = tempfile.TemporaryDirectory(prefix="watari-helpcfg-")
        self._saved_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._cfg.name
        self._saved_mem = wl.MEM
        self._home = tempfile.TemporaryDirectory(prefix="watari-helpchat-")
        wl.MEM = self._home.name

    def tearDown(self):
        wl.MEM = self._saved_mem
        self._home.cleanup()
        if self._saved_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._saved_xdg
        self._cfg.cleanup()

    def test_show_lists_bundled_prompt_templates_after_no_skills(self):
        rc, out, _err = _run(["chat", "--show"])
        self.assertEqual(rc, 0)
        cmd_line = out.splitlines()[-1]
        for name in ("remember", "organize", "profile", "forget", "goal", "watari-help"):
            self.assertIn(f"{name}.md", cmd_line)
        # --no-skills の後・--append-system-prompt の前に --prompt-template が並ぶ
        self.assertLess(cmd_line.index("--no-skills"), cmd_line.index("--prompt-template"))
        self.assertLess(cmd_line.index("--prompt-template"),
                        cmd_line.index("--append-system-prompt"))

    def test_show_has_explanatory_heading(self):
        rc, out, _err = _run(["chat", "--show"])
        self.assertEqual(rc, 0)
        self.assertIn("chat が実行するコマンド", out.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
