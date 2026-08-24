"""Thinking要約は会話ログでなく、差し替わる作業中の1行にだけ使う。"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROGRESS = ROOT / "src" / "watari_cli" / "pi" / "thinking-progress.mjs"
EXTENSION = ROOT / "src" / "watari_cli" / "pi" / "thinking-progress.ts"


def _latest_thinking(content: list[dict[str, str]]) -> str | None:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is required by the Pi runtime")
    script = (
        f"import {{ latestThinkingProgress }} from {json.dumps(PROGRESS.as_uri())};"
        "const content=JSON.parse(process.argv[1]);"
        "console.log(JSON.stringify(latestThinkingProgress({content})??null));"
    )
    result = subprocess.run(
        [node, "--input-type=module", "-e", script,
         json.dumps(content, ensure_ascii=False)],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class ThinkingProgressTest(unittest.TestCase):
    def test_latest_summary_becomes_one_plain_transient_line(self):
        content = [
            {"type": "thinking", "thinking": "**Inspecting configuration**\n\n**Mapping active processes**"},
            {"type": "toolCall", "name": "read"},
        ]
        self.assertEqual(_latest_thinking(content), "Mapping active processes")

    def test_missing_thinking_does_not_replace_working_line(self):
        self.assertIsNone(_latest_thinking([{"type": "text", "text": "回答です。"}]))

    def test_terminal_controls_are_removed_from_progress(self):
        content = [{"type": "thinking", "thinking": "\u001b[31m**Inspecting safely**\u001b[0m"}]
        self.assertEqual(_latest_thinking(content), "Inspecting safely")

    def test_extension_replaces_working_message_and_resets_after_agent(self):
        text = EXTENSION.read_text(encoding="utf-8")
        self.assertIn('pi.on("message_update"', text)
        self.assertIn("ctx.ui.setWorkingMessage(progress)", text)
        self.assertIn('pi.on("agent_end"', text)
        self.assertIn("ctx.ui.setWorkingMessage()", text)


if __name__ == "__main__":
    unittest.main()
