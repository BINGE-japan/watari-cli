"""chat 起動時の裏 dream の二重起動ガードの契約テスト（Popen には到達させない）。

- lock 無し=未実行、fresh ts=直近実行、古い ts＋死 pid=未実行、live pid=実行中。
- dream worker（WATARI_SKIP_AUTO_DREAM）は spawn しない＝再帰しない。
- 直近実行中は spawn しない（lock を書き換えない）。
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest

from watari_cli import cli


class DreamGuardTest(unittest.TestCase):
    def setUp(self):
        self._st = tempfile.TemporaryDirectory(prefix="watari-ad-")
        self._saved_state = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = self._st.name
        self._saved_skip = os.environ.pop("WATARI_SKIP_AUTO_DREAM", None)

    def tearDown(self):
        if self._saved_state is None:
            os.environ.pop("XDG_STATE_HOME", None)
        else:
            os.environ["XDG_STATE_HOME"] = self._saved_state
        if self._saved_skip is not None:
            os.environ["WATARI_SKIP_AUTO_DREAM"] = self._saved_skip
        else:
            os.environ.pop("WATARI_SKIP_AUTO_DREAM", None)
        self._st.cleanup()

    def _lock(self):
        return os.path.join(cli._state_dir(), "dream.lock")

    def _write_lock(self, pid, ts):
        with open(self._lock(), "w", encoding="utf-8") as f:
            json.dump({"pid": pid, "ts": ts}, f)

    def test_none_when_no_lock(self):
        self.assertFalse(cli._dream_recently(self._lock()))

    def test_fresh_ts_is_recent(self):
        self._write_lock(999999999, time.time())  # 死 pid だが ts が新しい
        self.assertTrue(cli._dream_recently(self._lock()))

    def test_old_ts_dead_pid_not_recent(self):
        self._write_lock(999999999, 0.0)
        self.assertFalse(cli._dream_recently(self._lock()))

    def test_live_pid_is_running(self):
        self._write_lock(os.getpid(), 0.0)  # 自プロセス=生存中
        self.assertTrue(cli._dream_recently(self._lock()))

    def test_spawn_skipped_for_worker(self):
        os.environ["WATARI_SKIP_AUTO_DREAM"] = "1"
        cli._spawn_background_dream("/nope", "pi", "/nope")
        self.assertFalse(os.path.exists(self._lock()))  # spawn せず lock も書かない

    def test_spawn_skipped_when_recent(self):
        self._write_lock(999999999, time.time())
        before = open(self._lock(), encoding="utf-8").read()
        cli._spawn_background_dream("/nope", "pi", "/nope")
        self.assertEqual(open(self._lock(), encoding="utf-8").read(), before)  # 変わらない


if __name__ == "__main__":
    unittest.main()
