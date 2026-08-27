"""組み込みtoolは通常表示から隠し、詳細はCtrl+Oへ分離する。"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "src" / "watari_cli" / "pi" / "compact-tools.mjs"
EXTENSION = ROOT / "src" / "watari_cli" / "pi" / "compact-tools.ts"


def _summarize(command: str) -> str:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is required by the Pi runtime")
    script = (
        f"import {{ summarizeCommand }} from {json.dumps(HELPER.as_uri())};"
        "console.log(JSON.stringify(summarizeCommand(process.argv[1])));"
    )
    result = subprocess.run(
        [node, "--input-type=module", "-e", script, command],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class CompactToolsTest(unittest.TestCase):
    def test_multiline_bash_body_is_not_shown_in_collapsed_summary(self):
        command = "python - <<'PY'\nimport requests\nprint('private body')\nPY"
        summary = _summarize(command)
        self.assertEqual(summary, "python - <<'PY' …")
        self.assertNotIn("requests", summary)

    def test_extension_overrides_builtin_renderers_without_changing_execution(self):
        text = EXTENSION.read_text(encoding="utf-8")
        for name in ("bash", "read", "edit", "write"):
            self.assertIn(f'name: "{name}"', text)
        self.assertIn("createBashTool(process.cwd())", text)
        self.assertIn("createBashToolDefinition(process.cwd())", text)
        self.assertIn("if (!options.expanded) return new Container()", text)
        self.assertIn("ctx.ui.setToolsExpanded(false)", text)

    def test_collapsed_tool_calls_leave_only_the_assistant_progress_line_visible(self):
        text = EXTENSION.read_text(encoding="utf-8")
        self.assertEqual(text.count("if (!context.expanded) return new Container()"), 4)
        self.assertNotIn("summarizeCommand(args.command)", text)
        self.assertNotIn("singleLine(args.path)", text)


if __name__ == "__main__":
    unittest.main()
