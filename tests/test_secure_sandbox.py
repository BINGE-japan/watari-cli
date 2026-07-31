"""Watari chat のPi道具をOS境界へ閉じ込める契約テスト。"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "src" / "watari_cli" / "pi" / "secure-sandbox.mjs"


def _node(expression: str, *args: str):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is required by the Pi runtime")
    script = f"import * as s from {json.dumps(CORE.as_uri())}; {expression}"
    result = subprocess.run(
        [node, "--input-type=module", "-e", script, *args],
        capture_output=True, text=True, timeout=20, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class SandboxPolicyTest(unittest.TestCase):
    def test_paths_outside_workspace_and_sensitive_project_files_are_denied(self):
        with tempfile.TemporaryDirectory(prefix="watari-sandbox-") as tmp:
            workspace = Path(tmp) / "project"
            workspace.mkdir()
            outside = Path(tmp) / "outside.txt"
            outside.write_text("secret", encoding="utf-8")
            (workspace / ".env").write_text("SYNTHETIC=secret", encoding="utf-8")
            result = _node(
                "const [w,o]=process.argv.slice(1); console.log(JSON.stringify({"
                "inside:s.isInsideWorkspace(w,w+'/src/a.ts'),"
                "outside:s.isInsideWorkspace(w,o),"
                "env:s.isSensitiveWorkspacePath(w,w+'/.env'),"
                "normal:s.isSensitiveWorkspacePath(w,w+'/src/a.ts')}));",
                str(workspace), str(outside),
            )
            self.assertEqual(result, {
                "inside": True, "outside": False, "env": True, "normal": False,
            })

    def test_symlink_escape_is_denied_even_when_the_target_does_not_exist(self):
        with tempfile.TemporaryDirectory(prefix="watari-sandbox-") as tmp:
            workspace = Path(tmp) / "project"
            workspace.mkdir()
            link = workspace / "dangling.txt"
            try:
                link.symlink_to(Path(tmp) / "outside" / "new.txt")
            except OSError as error:
                raise unittest.SkipTest(f"symlinks unavailable: {error}")
            result = _node(
                "const [w,p]=process.argv.slice(1); let blocked=false; "
                "try { await s.assertWorkspacePath(w,p,{allowMissing:true}); } catch { blocked=true; } "
                "console.log(JSON.stringify(blocked));",
                str(workspace), str(link),
            )
            self.assertTrue(result)

    def test_environment_is_allowlisted_not_copied(self):
        result = _node(
            "console.log(JSON.stringify(s.sandboxEnvironment({"
            "PATH:'/evil',HOME:'/home/real',OPENROUTER_API_KEY:'secret',TERM:'xterm'})));"
        )
        self.assertEqual(result["HOME"], "/tmp/watari-home")
        self.assertEqual(result["TERM"], "xterm")
        self.assertNotIn("OPENROUTER_API_KEY", result)
        self.assertNotEqual(result["PATH"], "/evil")

    def test_bubblewrap_hides_host_and_network_but_keeps_workspace_writable(self):
        bwrap = shutil.which("bwrap")
        if not bwrap:
            raise unittest.SkipTest("bubblewrap is required on Linux")
        with tempfile.TemporaryDirectory(prefix="watari-sandbox-") as tmp:
            workspace = Path(tmp) / "project"
            workspace.mkdir()
            (workspace / "visible.txt").write_text("visible", encoding="utf-8")
            (workspace / ".env").write_text("SYNTHETIC=hidden", encoding="utf-8")
            args = _node(
                "const w=process.argv[1]; const a=await s.buildBubblewrapArgs(w,[w+'/.env']);"
                "console.log(JSON.stringify(a));",
                str(workspace),
            )
            probe = (
                "set -e; test -r /tmp/watari-workspace/visible.txt; "
                "touch /tmp/watari-workspace/writable.txt; "
                "test ! -s /tmp/watari-workspace/.env; "
                f"test ! -s {workspace}/.env; "
                "test ! -e /home/binge/.config/watari/config.json; "
                "test ! -e /mnt/c/Users/BINGE; "
                "command -v node >/dev/null; command -v uv >/dev/null; "
                "command -v python3 >/dev/null; command -v git >/dev/null; command -v rg >/dev/null; "
                "! timeout 2 bash -c '</dev/tcp/github.com/443' 2>/dev/null"
            )
            result = subprocess.run(
                [bwrap, *args, "/bin/bash", "-lc", probe],
                capture_output=True, text=True, timeout=15, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((workspace / "writable.txt").exists())


if __name__ == "__main__":
    unittest.main()
