"""watari chat が Pi へ渡す起動コマンドの契約テスト。

ワタリは「オンデマンドで呼ぶスキル」でなく常時オンの人格。--skill 渡しだとモデルが自動発動せず
素の助手のまま応答する（クリーン環境で実測）。よって:
- 人格は `--append-system-prompt <SKILL.md>` でシステムプロンプトに常時注入する。
- `--no-skills` で他スキルの自動探索（~/.agents/skills 等の同名 "watari" 衝突含む）を切る。

config は XDG_CONFIG_HOME 配下なので隔離。cmd_chat は home の存在チェックだけなので wl.MEM を差し替える。
"""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest

from watari_cli.cli import _build_parser
from watari_cli.engine import watari_lib as wl


def _run(argv):
    args = _build_parser().parse_args(argv)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = args.func(args)
    return rc, out.getvalue(), err.getvalue()


class ChatLaunchTest(unittest.TestCase):
    def setUp(self):
        self._cfg = tempfile.TemporaryDirectory(prefix="watari-chatcfg-")
        self._saved_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._cfg.name
        self._saved_mem = wl.MEM
        self._home = tempfile.TemporaryDirectory(prefix="watari-chat-")
        wl.MEM = self._home.name  # chat は home の存在チェックだけ

    def tearDown(self):
        wl.MEM = self._saved_mem
        self._home.cleanup()
        if self._saved_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._saved_xdg
        self._cfg.cleanup()

    def test_persona_injected_as_system_prompt_not_ondemand_skill(self):
        rc, out, _ = _run(["chat", "--show"])
        self.assertEqual(rc, 0)
        self.assertIn("--no-skills", out)
        self.assertIn("--append-system-prompt", out)
        self.assertIn("SKILL.md", out)
        # 旧 `--skill <dir>`（オンデマンド＝自動発動しない）に戻っていないこと
        self.assertNotIn("--skill ", out)

    def test_extra_args_pass_through_after_persona(self):
        rc, out, _ = _run(["chat", "--show", "--", "-p", "hi"])
        self.assertEqual(rc, 0)
        self.assertIn("--append-system-prompt", out)
        self.assertIn("-p hi", out)


if __name__ == "__main__":
    unittest.main()
