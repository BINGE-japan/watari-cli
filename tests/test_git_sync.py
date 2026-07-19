"""カセット git 同期層の契約テスト（ローカル bare remote でオフライン検証）。

- git repo でない記憶は静かに no-op（ローカルのみ運用を壊さない）。
- setup_remote で init+remote+push、sync_after_write で push、sync_before_read で pull。
- remote 無し（ローカルのみ）でも commit は残る（履歴・バックアップになる）。
- install wizard の同期選択（--remote / --yes 既定ローカル / clone は origin 既設）。
"""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import tempfile
import unittest

from watari_cli import cli, git_sync
from watari_cli.cli import _build_parser


def _run(argv):
    args = _build_parser().parse_args(argv)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = args.func(args)
    return rc, out.getvalue(), err.getvalue()


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True)


def _ident(repo):
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")


class GitSyncTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="watari-gs-")
        self.root = self._tmp.name
        self.home = os.path.join(self.root, "cart")
        os.makedirs(self.home)
        with open(os.path.join(self.home, "life.log"), "w", encoding="utf-8") as f:
            f.write("a\n")

    def tearDown(self):
        self._tmp.cleanup()

    def _bare(self):
        bare = os.path.join(self.root, "remote.git")
        subprocess.run(["git", "init", "--bare", bare], check=True, capture_output=True)
        return bare

    def test_noop_when_not_a_repo(self):
        self.assertFalse(git_sync.is_repo(self.home))
        git_sync.sync_before_read(self.home)   # 例外を出さない
        git_sync.sync_after_write(self.home)
        self.assertFalse(os.path.isdir(os.path.join(self.home, ".git")))  # repo 化もしない

    def test_setup_remote_pushes_content(self):
        bare = self._bare()
        ok, msg = git_sync.setup_remote(self.home, bare)
        self.assertTrue(ok, msg)
        self.assertTrue(git_sync.is_repo(self.home) and git_sync.has_remote(self.home))
        clone = os.path.join(self.root, "clone")
        subprocess.run(["git", "clone", bare, clone], check=True, capture_output=True)
        self.assertTrue(os.path.isfile(os.path.join(clone, "life.log")))  # push されている

    def test_after_write_pushes_and_before_read_pulls(self):
        bare = self._bare()
        git_sync.setup_remote(self.home, bare)
        # 別マシン相当が remote に push
        other = os.path.join(self.root, "other")
        subprocess.run(["git", "clone", bare, other], check=True, capture_output=True)
        _ident(other)
        with open(os.path.join(other, "learning.log"), "w", encoding="utf-8") as f:
            f.write("b\n")
        _git(other, "add", "-A"); _git(other, "commit", "-m", "x"); _git(other, "push")
        # 読む前 sync で他マシン分が入る
        git_sync.sync_before_read(self.home)
        self.assertTrue(os.path.isfile(os.path.join(self.home, "learning.log")))
        # 書いた後 sync で自分の分が remote に載る
        with open(os.path.join(self.home, "new.log"), "w", encoding="utf-8") as f:
            f.write("c\n")
        git_sync.sync_after_write(self.home)
        _git(other, "pull")
        self.assertTrue(os.path.isfile(os.path.join(other, "new.log")))

    def test_local_only_commits_without_remote(self):
        subprocess.run(["git", "-C", self.home, "init"], check=True, capture_output=True)
        self.assertTrue(git_sync.is_repo(self.home))
        self.assertFalse(git_sync.has_remote(self.home))
        git_sync.sync_after_write(self.home)   # commit のみ（remote 無し）
        log = subprocess.run(["git", "-C", self.home, "log", "--oneline"],
                             capture_output=True, text=True)
        self.assertTrue(log.stdout.strip())    # 履歴に残る


class InstallSyncChoiceTest(unittest.TestCase):
    def _plan(self, argv):
        return cli._install_wizard(_build_parser().parse_args(argv))

    def test_remote_flag_sets_git_remote(self):
        plan = self._plan(["install", "--yes", "--remote", "git@x:me/mem.git"])
        self.assertEqual(plan["git_remote"], "git@x:me/mem.git")

    def test_yes_defaults_local_only(self):
        self.assertIsNone(self._plan(["install", "--yes"])["git_remote"])

    def test_clone_leaves_remote_to_origin(self):
        plan = self._plan(["install", "--from", "git@x:me/mem.git"])
        self.assertEqual(plan["mode"], "clone")
        self.assertIsNone(plan["git_remote"])

    def test_dry_run_shows_sync_line(self):
        rc, out, _ = _run(["install", "--dry-run", "--yes", "--remote", "git@x:y.git"])
        self.assertEqual(rc, 0)
        self.assertIn("同期", out)
        self.assertIn("git@x:y.git", out)


if __name__ == "__main__":
    unittest.main()
