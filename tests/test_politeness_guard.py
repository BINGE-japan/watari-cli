"""Watari の敬語はモデル任せにせず、表示・保存前に決定論で守る。"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "src" / "watari_cli" / "pi" / "politeness.mjs"


def _guard(text: str) -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is required by the Pi runtime")
    script = (
        "import { guardText } from " + json.dumps(GUARD.as_uri()) + ";"
        "const input = JSON.parse(process.argv[1]);"
        "console.log(JSON.stringify(guardText(input)));"
    )
    result = subprocess.run(
        [node, "--input-type=module", "-e", script, json.dumps(text, ensure_ascii=False)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class PolitenessGuardTest(unittest.TestCase):
    def test_observed_casual_greeting_is_rewritten(self):
        guarded = _guard("おす、ワタリです。今日は何やります？")
        self.assertEqual(guarded["text"], "こんにちは、ワタリです。今日は何をしますか。")
        self.assertTrue(guarded["changed"])
        self.assertFalse(guarded["blocked"])

    def test_polite_answer_is_unchanged(self):
        text = "承知しました。現在の設定を確認します。"
        self.assertEqual(_guard(text), {"text": text, "changed": False, "blocked": False})

    def test_unknown_casual_answer_fails_closed(self):
        guarded = _guard("うん、それでいいよ。次も任せて。")
        self.assertTrue(guarded["changed"])
        self.assertTrue(guarded["blocked"])
        self.assertNotIn("いいよ", guarded["text"])
        self.assertIn("敬語", guarded["text"])

    def test_quoted_casual_words_do_not_trigger_guard(self):
        text = "「だよ」はカジュアルな終助詞です。"
        self.assertEqual(_guard(text), {"text": text, "changed": False, "blocked": False})


if __name__ == "__main__":
    unittest.main()
