"""Project Pi must never finish a modifying task with an uncommitted worktree."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "AGENTS.md"
GUARD = ROOT / ".pi" / "extensions" / "commit-worktree" / "guard.mjs"
EXTENSION = ROOT / ".pi" / "extensions" / "commit-worktree" / "index.ts"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False,
    )


def _run_guard(repo: Path, baseline: str, prompt: str) -> dict[str, object]:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is required by Pi extensions")
    script = f"""
import {{ ensureCommittedWorktree }} from {json.dumps(GUARD.as_uri())};
import {{ spawnSync }} from "node:child_process";
const exec = async (command, args) => {{
  const result = spawnSync(command, args, {{ cwd: process.cwd(), encoding: "utf8" }});
  return {{ stdout: result.stdout || "", stderr: result.stderr || "", code: result.status ?? 1 }};
}};
const result = await ensureCommittedWorktree(exec, {json.dumps(baseline)}, {json.dumps(prompt)});
console.log(JSON.stringify(result));
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=repo, capture_output=True, text=True, timeout=15, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class ProjectPiCommitGuardTest(unittest.TestCase):
    def _repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        self.assertEqual(_git(repo, "init").returncode, 0)
        self.assertEqual(_git(repo, "config", "user.email", "pi@example.invalid").returncode, 0)
        self.assertEqual(_git(repo, "config", "user.name", "Pi Test").returncode, 0)
        (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        self.assertEqual(_git(repo, "add", "tracked.txt").returncode, 0)
        self.assertEqual(_git(repo, "commit", "-m", "base").returncode, 0)
        return tmp, repo

    def test_project_rules_require_a_clean_commit_before_final_answer(self):
        text = RULES.read_text(encoding="utf-8")
        self.assertIn("Commit completion is mandatory", text)
        self.assertIn("git status --porcelain", text)
        self.assertIn("Do not send the final answer", text)

    def test_project_extension_guards_final_answers_and_shutdown(self):
        text = EXTENSION.read_text(encoding="utf-8")
        self.assertIn('pi.on("before_agent_start"', text)
        self.assertIn('pi.on("message_end"', text)
        self.assertIn('pi.on("session_shutdown"', text)

    def test_fallback_commits_changes_created_from_a_clean_baseline(self):
        tmp, repo = self._repo()
        try:
            (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
            result = _run_guard(repo, "", "Fix duplicate warnings")
            self.assertEqual(result["status"], "committed")
            self.assertEqual(_git(repo, "status", "--porcelain").stdout, "")
            self.assertIn("Fix duplicate warnings", _git(repo, "log", "-1", "--pretty=%s").stdout)
        finally:
            tmp.cleanup()

    def test_fallback_never_sweeps_preexisting_changes_into_a_commit(self):
        tmp, repo = self._repo()
        try:
            (repo / "tracked.txt").write_text("user change\n", encoding="utf-8")
            baseline = _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
            (repo / "new.txt").write_text("agent change\n", encoding="utf-8")
            result = _run_guard(repo, baseline, "Do another task")
            self.assertEqual(result["status"], "preexisting-dirty")
            self.assertNotEqual(_git(repo, "status", "--porcelain").stdout, "")
            self.assertEqual(_git(repo, "log", "-1", "--pretty=%s").stdout.strip(), "base")
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
