"""質問への回答は観測済みでなければ表示しない。推測表現は警告を添えて表示する。"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "src" / "watari_cli" / "pi" / "verification.mjs"
GUARD_EXTENSION = ROOT / "src" / "watari_cli" / "pi" / "verification-guard.ts"
SKILL = ROOT / "src" / "watari_cli" / "skill" / "SKILL.md"


def _call(function: str, *args):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is required by the Pi runtime")
    script = (
        f"import {{ {function} }} from {json.dumps(GUARD.as_uri())};"
        "const args=JSON.parse(process.argv[1]);"
        f"console.log(JSON.stringify({function}(...args)));"
    )
    result = subprocess.run(
        [node, "--input-type=module", "-e", script,
         json.dumps(args, ensure_ascii=False)],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class VerificationGuardTest(unittest.TestCase):
    def test_questions_require_observation(self):
        self.assertTrue(_call("requiresObservation", "右のペインは直っていますか？"))
        self.assertTrue(_call("requiresObservation", "微分とは何ですか"))

    def test_non_questions_do_not_require_observation(self):
        self.assertFalse(_call("requiresObservation", "こんにちは"))
        self.assertFalse(_call("requiresObservation", "この文章を敬語に書き換えて"))

    def test_unverified_answer_is_shown_with_warning(self):
        text = "直っています。"
        guarded = _call("guardAnswer", text, True, False)
        self.assertFalse(guarded["blocked"])
        self.assertIn(text, guarded["text"])
        self.assertIn("未確認", guarded["text"])

    def test_verified_answer_passes(self):
        text = "実ファイルを確認したところ、設定は有効です。"
        self.assertEqual(
            _call("guardAnswer", text, True, True),
            {"text": text, "changed": False, "blocked": False},
        )

    def test_speculation_is_shown_with_warning(self):
        text = "おそらく設定は有効です。"
        guarded = _call("guardAnswer", text, True, True)
        self.assertFalse(guarded["blocked"])
        self.assertIn(text, guarded["text"])
        self.assertIn("推測", guarded["text"])

    def test_unverified_speculation_is_shown_with_one_combined_warning(self):
        text = "おそらく設定は有効です。"
        guarded = _call("guardAnswer", text, True, False)
        self.assertFalse(guarded["blocked"])
        self.assertIn(text, guarded["text"])
        self.assertIn("未確認", guarded["text"])
        self.assertIn("推測", guarded["text"])
        self.assertEqual(guarded["text"].count("⚠"), 1)

    def test_prompts_do_not_force_conversation_stopping_fallback(self):
        extension = GUARD_EXTENSION.read_text(encoding="utf-8")
        skill = SKILL.read_text(encoding="utf-8")
        self.assertNotIn("確認手段がない場合は断定せず、その事実だけを伝えてください", extension)
        self.assertNotIn("確認できないため断定しません", skill)
        self.assertIn("推測であることを明示", extension)
        self.assertIn("推測であることを明示", skill)

    def test_clarifying_question_is_allowed_without_observation(self):
        text = "どのファイルを指していますか？"
        self.assertEqual(
            _call("guardAnswer", text, True, False),
            {"text": text, "changed": False, "blocked": False},
        )


if __name__ == "__main__":
    unittest.main()
