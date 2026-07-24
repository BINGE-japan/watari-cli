"""watari chatの自動更新はmainの安全な早送りだけを適用する。"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from watari_cli import updater


class FakeRunner:
    def __init__(self, responses):
        self.responses = {tuple(key): list(value) for key, value in responses.items()}
        self.calls = []

    def __call__(self, command, **_kwargs):
        key = tuple(command)
        self.calls.append(key)
        queue = self.responses.get(key)
        if not queue:
            raise AssertionError(f"unexpected command: {command}")
        return queue.pop(0)


def _done(stdout="", code=0, stderr=""):
    return subprocess.CompletedProcess([], code, stdout, stderr)


class SourceDiscoveryTest(unittest.TestCase):
    def test_local_direct_url_resolves_git_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            direct = {"url": root.as_uri(), "dir_info": {}}
            self.assertEqual(updater.source_checkout_from_direct_url(direct), root)

    def test_non_local_install_is_not_modified(self):
        self.assertIsNone(updater.source_checkout_from_direct_url({
            "url": "https://example.test/watari.whl"
        }))

    def test_uv_tool_python_symlink_is_recognized_by_its_installed_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool_dir = Path(tmp) / "tools"
            executable = tool_dir / "watari-cli" / "bin" / "python"
            executable.parent.mkdir(parents=True)
            executable.symlink_to(Path(tmp) / "managed-python")
            self.assertTrue(updater.executable_is_in_tool_dir(executable, tool_dir))


class InstalledPayloadTest(unittest.TestCase):
    def test_detects_source_and_installed_package_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_package = root / "source" / "src" / "watari_cli"
            installed_package = root / "installed" / "watari_cli"
            source_package.mkdir(parents=True)
            installed_package.mkdir(parents=True)
            (source_package / "guard.mjs").write_text("new", encoding="utf-8")
            (installed_package / "guard.mjs").write_text("old", encoding="utf-8")
            self.assertFalse(updater.installed_payload_matches_source(
                root / "source", installed_package=installed_package))
            (installed_package / "guard.mjs").write_text("new", encoding="utf-8")
            self.assertTrue(updater.installed_payload_matches_source(
                root / "source", installed_package=installed_package))


class CheckoutUpdateTest(unittest.TestCase):
    def _base_responses(self, root: Path):
        return {
            ("git", "-C", str(root), "branch", "--show-current"): [_done("main\n")],
            ("git", "-C", str(root), "status", "--porcelain"): [_done("")],
            ("git", "-C", str(root), "rev-parse", "HEAD"): [_done("aaa111\n")],
            ("git", "-C", str(root), "fetch", "--quiet", "origin", "main"): [_done()],
            ("git", "-C", str(root), "rev-parse", "refs/remotes/origin/main"): [_done("bbb222\n")],
            ("git", "-C", str(root), "merge-base", "--is-ancestor", "aaa111", "bbb222"): [_done()],
            ("git", "-C", str(root), "log", "--reverse", "--format=%s", "aaa111..bbb222"): [
                _done("作業表示を1行化\n自動更新を追加\n")
            ],
            ("git", "-C", str(root), "merge", "--ff-only", "bbb222"): [_done()],
            ("uv", "tool", "install", "--force", "--refresh", str(root)): [_done()],
        }

    def test_current_checkout_reinstalls_when_installed_payload_is_stale(self):
        root = Path("/tmp/example-watari")
        base = ("git", "-C", str(root))
        runner = FakeRunner({
            (*base, "branch", "--show-current"): [_done("main\n")],
            (*base, "status", "--porcelain"): [_done("")],
            (*base, "rev-parse", "HEAD"): [_done("aaa111\n")],
            (*base, "fetch", "--quiet", "origin", "main"): [_done()],
            (*base, "rev-parse", "refs/remotes/origin/main"): [_done("aaa111\n")],
            ("uv", "tool", "install", "--force", "--refresh", str(root)): [_done()],
        })
        result = updater.update_checkout(
            root, run=runner, installed_matches=lambda _source: False)
        self.assertEqual(result.status, "repaired")
        self.assertIn(("uv", "tool", "install", "--force", "--refresh", str(root)), runner.calls)

    def test_current_checkout_skips_reinstall_when_installed_payload_matches(self):
        root = Path("/tmp/example-watari")
        base = ("git", "-C", str(root))
        runner = FakeRunner({
            (*base, "branch", "--show-current"): [_done("main\n")],
            (*base, "status", "--porcelain"): [_done("")],
            (*base, "rev-parse", "HEAD"): [_done("aaa111\n")],
            (*base, "fetch", "--quiet", "origin", "main"): [_done()],
            (*base, "rev-parse", "refs/remotes/origin/main"): [_done("aaa111\n")],
        })
        result = updater.update_checkout(
            root, run=runner, installed_matches=lambda _source: True)
        self.assertEqual(result.status, "current")
        self.assertFalse(any(call[:2] == ("uv", "tool") for call in runner.calls))

    def test_remote_main_fast_forward_updates_and_reports_changes(self):
        root = Path("/tmp/example-watari")
        runner = FakeRunner(self._base_responses(root))
        result = updater.update_checkout(root, run=runner)
        self.assertEqual(result.status, "updated")
        self.assertEqual(result.before, "aaa111")
        self.assertEqual(result.after, "bbb222")
        self.assertEqual(result.changes, ["作業表示を1行化", "自動更新を追加"])
        self.assertIn(("uv", "tool", "install", "--force", "--refresh", str(root)), runner.calls)

    def test_dirty_checkout_is_left_untouched(self):
        root = Path("/tmp/example-watari")
        runner = FakeRunner({
            ("git", "-C", str(root), "branch", "--show-current"): [_done("main\n")],
            ("git", "-C", str(root), "status", "--porcelain"): [_done(" M README.md\n")],
        })
        result = updater.update_checkout(root, run=runner)
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.reason, "dirty")
        self.assertFalse(any(call[:2] == ("uv", "tool") for call in runner.calls))

    def test_non_main_checkout_is_left_untouched(self):
        root = Path("/tmp/example-watari")
        runner = FakeRunner({
            ("git", "-C", str(root), "branch", "--show-current"): [_done("feature\n")],
        })
        result = updater.update_checkout(root, run=runner)
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.reason, "branch")

    def test_failed_reinstall_rolls_checkout_back(self):
        root = Path("/tmp/example-watari")
        responses = self._base_responses(root)
        responses[("uv", "tool", "install", "--force", "--refresh", str(root))] = [
            _done(code=1, stderr="install failed")
        ]
        responses[("git", "-C", str(root), "reset", "--hard", "aaa111")] = [_done()]
        runner = FakeRunner(responses)
        result = updater.update_checkout(root, run=runner)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.reason, "install")
        self.assertIn(("git", "-C", str(root), "reset", "--hard", "aaa111"), runner.calls)


class UpdateNoticeTest(unittest.TestCase):
    def test_repair_notice_is_distinct_from_remote_update(self):
        result = updater.UpdateResult(
            status="repaired", before="aaa111", after="aaa111")
        self.assertEqual(
            updater.notice_lines(result),
            ["ワタリの反映漏れを修復しました（aaa111）。"],
        )

    def test_notice_lists_completed_changes(self):
        result = updater.UpdateResult(
            status="updated", before="aaa111", after="bbb222",
            changes=["作業表示を1行化", "自動更新を追加"],
        )
        self.assertEqual(updater.notice_lines(result), [
            "ワタリを更新しました（aaa111 → bbb222）。",
            "  ・作業表示を1行化",
            "  ・自動更新を追加",
        ])

    def test_restart_passes_completed_notice_to_new_process(self):
        result = updater.UpdateResult(
            status="updated", before="aaa111", after="bbb222", changes=["更新内容"])
        captured = {}

        def fake_exec(executable, argv, env):
            captured.update(executable=executable, argv=argv, env=env)
            raise RuntimeError("exec replaces the process in production")

        with self.assertRaisesRegex(RuntimeError, "replaces"):
            updater.restart_with_notice(
                result, executable="/tmp/bin/watari",
                argv=["watari", "chat"], exec_fn=fake_exec)
        self.assertEqual(captured["executable"], "/tmp/bin/watari")
        self.assertEqual(captured["argv"], ["/tmp/bin/watari", "chat"])
        payload = json.loads(captured["env"][updater.NOTICE_ENV])
        self.assertEqual(payload["changes"], ["更新内容"])
        self.assertNotIn(updater.NOTICE_ENV, os.environ)


if __name__ == "__main__":
    unittest.main()
