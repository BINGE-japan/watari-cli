"""作業表示は通常1行、Ctrl+O展開時はPi本来の詳細を保つ。"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUIET_UI = ROOT / "src" / "watari_cli" / "pi" / "quiet-ui.mjs"


def _compact(lines: list[str], expanded: bool) -> list[str]:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is required by the Pi runtime")
    script = (
        f"import {{ compactToolLines }} from {json.dumps(QUIET_UI.as_uri())};"
        "const [lines,expanded]=JSON.parse(process.argv[1]);"
        "console.log(JSON.stringify(compactToolLines(lines,expanded)));"
    )
    result = subprocess.run(
        [node, "--input-type=module", "-e", script,
         json.dumps([lines, expanded], ensure_ascii=False)],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


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


if __name__ == "__main__":
    unittest.main()
