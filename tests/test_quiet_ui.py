"""作業表示は通常1行、Ctrl+O展開時はPi本来の詳細を保つ。"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUIET_UI = ROOT / "src" / "watari_cli" / "pi" / "quiet-ui.mjs"


def _run_node(script: str, argument: object) -> object:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is required by the Pi runtime")
    result = subprocess.run(
        [node, "--input-type=module", "-e", script,
         json.dumps(argument, ensure_ascii=False)],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def _compact(lines: list[str], expanded: bool) -> list[str]:
    script = (
        f"import {{ compactToolLines }} from {json.dumps(QUIET_UI.as_uri())};"
        "const [lines,expanded]=JSON.parse(process.argv[1]);"
        "console.log(JSON.stringify(compactToolLines(lines,expanded)));"
    )
    return _run_node(script, [lines, expanded])


def _prepare_assistant_message(message: dict[str, object]) -> dict[str, object]:
    script = (
        f"import {{ prepareAssistantMessage }} from {json.dumps(QUIET_UI.as_uri())};"
        "const message=JSON.parse(process.argv[1]);"
        "const mark=(name)=>(value)=>({...value,guards:[...(value.guards??[]),name]});"
        "const displayed=prepareAssistantMessage(message,mark('politeness'),mark('verification'));"
        "console.log(JSON.stringify(displayed));"
    )
    return _run_node(script, message)


class CompactToolLinesTest(unittest.TestCase):
    def test_collapsed_view_keeps_only_the_action_line(self):
        lines = ["", "   ", " read src/example.py ", " output line ", "   "]
        self.assertEqual(_compact(lines, False), [" read src/example.py "])

    def test_expanded_view_keeps_pi_native_output(self):
        lines = ["", " read src/example.py ", " output line "]
        self.assertEqual(_compact(lines, True), lines)

    def test_ansi_only_padding_is_not_selected(self):
        lines = ["\u001b[48;2;1;2;3m   \u001b[0m", "\u001b[32m edit file.py \u001b[0m"]
        self.assertEqual(_compact(lines, False), ["\u001b[32m edit file.py \u001b[0m"])


class PrepareAssistantMessageTest(unittest.TestCase):
    def test_completed_intermediate_prose_stays_visible_with_tool_call(self):
        message = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "確認して進めます。"},
                {"type": "toolCall", "name": "read", "arguments": {}},
            ],
            "stopReason": "toolUse",
        }

        displayed = _prepare_assistant_message(message)

        self.assertEqual(displayed["content"][0]["text"], "確認して進めます。")
        self.assertEqual(displayed["guards"], ["politeness"])

    def test_streaming_partial_prose_stays_hidden_until_guarded(self):
        message = {
            "role": "assistant",
            "content": [{"type": "text", "text": "確認して"}],
        }

        displayed = _prepare_assistant_message(message)

        self.assertEqual(displayed["content"][0]["text"], "")
        self.assertNotIn("guards", displayed)

    def test_completed_final_answer_uses_both_guards(self):
        message = {
            "role": "assistant",
            "content": [{"type": "text", "text": "確認しました。"}],
            "stopReason": "stop",
        }

        displayed = _prepare_assistant_message(message)

        self.assertEqual(displayed["content"][0]["text"], "確認しました。")
        self.assertEqual(displayed["guards"], ["politeness", "verification"])


if __name__ == "__main__":
    unittest.main()
