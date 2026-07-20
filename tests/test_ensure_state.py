"""_ensure_state: clone 直後(state 無し)や pull 後(log が state より新しい)に state を再生成する。"""
import json
import os
import tempfile
import unittest

from watari_cli.cli import _ensure_state
from watari_cli.engine import watari_lib as wl


ROW = {"ts": "2026-07-20T00:00:00.000Z", "source": "watari", "kind": "thread",
       "topic": "t", "note": "n", "refs": {"uuid": "u1"}}


class EnsureStateTest(unittest.TestCase):
    def setUp(self):
        self._saved_mem = wl.MEM
        self._tmp = tempfile.TemporaryDirectory(prefix="watari-ensure-")
        wl.MEM = self._tmp.name
        for genre in ("life", "learning"):
            os.makedirs(os.path.join(wl.MEM, genre), exist_ok=True)
            open(wl.log_path(genre), "w", encoding="utf-8").close()
        with open(wl.log_path("life"), "w", encoding="utf-8") as f:
            f.write(json.dumps(ROW, ensure_ascii=False) + "\n")

    def tearDown(self):
        wl.MEM = self._saved_mem
        self._tmp.cleanup()

    def _state(self, genre):
        p = wl.state_path(genre)
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None

    def test_missing_state_is_rebuilt(self):
        self.assertIsNone(self._state("life"))  # clone 直後相当（gitignore で state は来ない）
        _ensure_state()
        st = self._state("life")
        self.assertIsNotNone(st)
        self.assertEqual([t["topic"] for t in st["open_threads"]], ["t"])
        self.assertIsNotNone(self._state("learning"))  # 全ジャンル書き出される

    def test_stale_state_is_rebuilt(self):
        _ensure_state()
        # pull で log だけが進んだ状況を再現（state の mtime を過去に倒す）
        row2 = dict(ROW, topic="t2", refs={"uuid": "u2"})
        with open(wl.log_path("life"), "a", encoding="utf-8") as f:
            f.write(json.dumps(row2, ensure_ascii=False) + "\n")
        os.utime(wl.state_path("life"), (1, 1))
        _ensure_state()
        topics = {t["topic"] for t in self._state("life")["open_threads"]}
        self.assertEqual(topics, {"t", "t2"})

    def test_fresh_state_is_untouched(self):
        _ensure_state()
        before = os.path.getmtime(wl.state_path("life"))
        _ensure_state()
        after = os.path.getmtime(wl.state_path("life"))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
