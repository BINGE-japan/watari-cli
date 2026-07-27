"""Watari exposes persistent balanced, fast, and full-memory performance modes."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from watari_cli import config
from watari_cli.cli import _build_parser

ROOT = Path(__file__).resolve().parents[1]
PERFORMANCE = ROOT / "src" / "watari_cli" / "pi" / "performance.mjs"
EXTENSION = ROOT / "src" / "watari_cli" / "pi" / "performance.ts"
MEMORY = ROOT / "src" / "watari_cli" / "pi" / "memory-context.mjs"
VERIFICATION = ROOT / "src" / "watari_cli" / "pi" / "verification-guard.ts"


def _run(argv: list[str]) -> tuple[int, str, str]:
    args = _build_parser().parse_args(argv)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = args.func(args)
    return rc, out.getvalue(), err.getvalue()


def _mode_contexts() -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is required by the Pi runtime")
    life = {
        "profile": {"name": "binge", "style": "one step"},
        "open_threads": [
            {"topic": f"thread-{i}", "note": "pending " + "x" * 200,
             "last": "2026-01-01T00:00:00.000Z"}
            for i in range(20)
        ],
        "interests": {
            f"interest-{i}": {"note": "interest " + "y" * 200,
                              "last": "2026-01-01T00:00:00.000Z"}
            for i in range(20)
        },
    }
    learning = {"domains": {"web": {"topics": {
        f"topic-{i}": {"note": f"full detail {i} " + "z" * 300,
                        "mastery": 2, "last": "2026-01-01T00:00:00.000Z",
                        "freshness": "2026-01-01T00:00:00.000Z", "related": []}
        for i in range(80)
    }}}}
    script = (
        f"import {{ buildMemoryContext }} from {json.dumps(MEMORY.as_uri())};"
        f"import {{ performanceMemoryOptions }} from {json.dumps(PERFORMANCE.as_uri())};"
        "import {readFileSync} from 'node:fs';"
        "const [life,learning]=JSON.parse(readFileSync(0,'utf8'));"
        "const out={};"
        "for(const mode of ['fast','balanced','butler'])"
        " out[mode]=buildMemoryContext(life,learning,'topic-79',performanceMemoryOptions(mode));"
        "console.log(JSON.stringify(out));"
    )
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        input=json.dumps([life, learning]), capture_output=True, text=True,
        timeout=15, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class PerformanceConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="watari-performance-")
        self.saved = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self.tmp.name

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self.saved
        self.tmp.cleanup()

    def test_balanced_is_default_and_cli_persists_selection(self):
        self.assertEqual(config.load_performance_mode(), "balanced")
        rc, out, err = _run(["performance", "--set", "fast"])
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("爆速", out)
        self.assertEqual(config.load_performance_mode(), "fast")
        self.assertEqual(config.load_config()["performance"], "fast")

    def test_invalid_saved_mode_fails_closed_to_balanced(self):
        config.save_config(performance="unknown")
        self.assertEqual(config.load_performance_mode(), "balanced")


class PerformanceRuntimeTest(unittest.TestCase):
    def test_modes_have_distinct_memory_budgets(self):
        contexts = _mode_contexts()
        compact = lambda value: len(json.dumps(value, ensure_ascii=False,
                                                separators=(",", ":")).encode())
        self.assertLessEqual(compact(contexts["fast"]), 4_000)
        self.assertEqual(contexts["fast"]["catalog"],
                         {"threads": [], "interests": [], "learning": {}})
        self.assertLessEqual(compact(contexts["balanced"]), 16_000)
        self.assertTrue(contexts["butler"]["full_context"])
        self.assertIn("full detail 0", json.dumps(contexts["butler"], ensure_ascii=False))
        self.assertGreater(compact(contexts["butler"]), compact(contexts["balanced"]))

    def test_slash_command_selects_mode_and_controls_thinking(self):
        text = EXTENSION.read_text(encoding="utf-8")
        self.assertIn('pi.registerCommand("performance"', text)
        self.assertIn("ctx.ui.select", text)
        self.assertIn("pi.setThinkingLevel", text)
        self.assertIn('pi.exec("watari", ["performance", "--set", mode])', text)

    def test_fast_mode_removes_the_extra_evidence_round_trip(self):
        text = VERIFICATION.read_text(encoding="utf-8")
        self.assertIn("automaticallyAcceptEvidence", text)
        self.assertIn("state.evidenceAccepted = true", text)


if __name__ == "__main__":
    unittest.main()
