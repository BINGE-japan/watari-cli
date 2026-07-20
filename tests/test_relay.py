"""chat 中継スレッドの契約テスト（スレッドは回さず tick 単位で検証）。

- 本文抽出：user/assistant の text だけ（thinking/toolcall/toolResult は除外）。
- バイトオフセット tail：新規行だけ抽出し offset を進める。
- クラウド送信：成功で queue クリア、offline は queue に繰り越し→復帰後に再送。
- 未認証（get_store None）は start() が no-op。
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from watari_cli import cloud, relay
from watari_cli.engine.watari_lib import fmt_ts, now_utc


class _Base(unittest.TestCase):
    def setUp(self):
        self._st = tempfile.TemporaryDirectory(prefix="watari-relay-state-")
        self._saved_state = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = self._st.name
        self._pi = tempfile.TemporaryDirectory(prefix="watari-relay-pi-")
        self.pi_store = self._pi.name

    def tearDown(self):
        if self._saved_state is None:
            os.environ.pop("XDG_STATE_HOME", None)
        else:
            os.environ["XDG_STATE_HOME"] = self._saved_state
        self._st.cleanup()
        self._pi.cleanup()

    def _session(self, name, records):
        d = os.path.join(self.pi_store, "proj")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return p


class FakeStore(cloud.CloudStore):
    def __init__(self, fail=False):
        self.data: dict = {}
        self.fail = fail

    def append(self, name, text):
        if self.fail:
            raise cloud.CloudError("offline")
        self.data[name] = self.data.get(name, "") + text

    def read(self, name):
        return self.data.get(name, "")

    def write(self, name, text):
        self.data[name] = text

    def list(self):
        return []

    def delete(self, name):
        self.data.pop(name, None)


class TextExtractTest(unittest.TestCase):
    def test_string_content(self):
        self.assertEqual(relay._message_text({"content": "hi"}), "hi")

    def test_only_text_blocks(self):
        msg = {"content": [{"type": "text", "text": "a"},
                           {"type": "thinking", "text": "secret"},
                           {"type": "toolCall", "toolName": "bash"}]}
        self.assertEqual(relay._message_text(msg), "a")


class ToLineTest(_Base):
    def _r(self):
        return relay.Relay(self.pi_store, "m1")

    def test_roles_and_filtering(self):
        r, meta = self._r(), {"cwd": "/w"}
        u = r._to_line(json.dumps({"type": "message", "id": "t1",
            "timestamp": "2026-07-19T00:00:00.000Z",
            "message": {"role": "user", "content": "hello"}}), meta)
        self.assertIn('"role": "user"', u)
        self.assertIn('"machine": "m1"', u)
        self.assertIn('"cwd": "/w"', u)
        a = r._to_line(json.dumps({"type": "message", "id": "t2",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}}), meta)
        self.assertIn('"role": "assistant"', a)
        self.assertIsNone(r._to_line(json.dumps({"type": "message", "id": "t3",
            "message": {"role": "toolResult", "content": [{"type": "text", "text": "x"}]}}), meta))
        self.assertIsNone(r._to_line(json.dumps({"type": "bashExecution"}), meta))
        self.assertIsNone(r._to_line("not json", meta))

    def test_line_carries_session(self):
        r = self._r()
        line = r._to_line(json.dumps({"type": "message", "id": "t1",
            "timestamp": "2026-07-19T00:00:00.000Z",
            "message": {"role": "user", "content": "hi"}}), {"cwd": "/w", "session": "SESS"})
        self.assertIn('"session": "SESS"', line)
        self.assertIn('"turn_id": "t1"', line)


class ExtractTest(_Base):
    def test_extract_new_then_empty(self):
        self._session("s.jsonl", [
            {"type": "session", "id": "S", "cwd": "/proj", "timestamp": "2026-07-19T00:00:00.000Z"},
            {"type": "message", "id": "a", "timestamp": "2026-07-19T00:00:01.000Z",
             "message": {"role": "user", "content": "q"}},
            {"type": "message", "id": "b", "timestamp": "2026-07-19T00:00:02.000Z",
             "message": {"role": "assistant", "content": [{"type": "text", "text": "ans"}]}},
            {"type": "message", "id": "c",
             "message": {"role": "toolResult", "content": [{"type": "text", "text": "t"}]}},
        ])
        r = relay.Relay(self.pi_store, "m1")
        lines = r._extract_new()
        self.assertEqual(len(lines), 2)          # user + assistant のみ
        self.assertIn('"cwd": "/proj"', lines[0])
        self.assertEqual(r._extract_new(), [])   # 2 回目は新規なし（offset 前進）


class TickFlushTest(_Base):
    def _one_user(self):
        self._session("s.jsonl", [
            {"type": "session", "id": "S", "cwd": "/p", "timestamp": "2026-07-19T00:00:00.000Z"},
            {"type": "message", "id": "a", "timestamp": "2026-07-19T00:00:01.000Z",
             "message": {"role": "user", "content": "hi"}},
        ])

    def test_tick_sends_and_clears_queue(self):
        self._one_user()
        r = relay.Relay(self.pi_store, "m1")
        r._store = FakeStore()
        r._tick()
        self.assertIn('"text": "hi"', r._store.data["transcripts-m1.jsonl"])
        with open(relay._queue_path(), encoding="utf-8") as f:
            self.assertEqual(f.read(), "")

    def test_offline_keeps_queue_then_resends(self):
        self._one_user()
        r = relay.Relay(self.pi_store, "m1")
        r._store = FakeStore(fail=True)
        r._tick()  # 送信失敗 → queue に残る
        with open(relay._queue_path(), encoding="utf-8") as f:
            self.assertIn("hi", f.read())
        r._store = FakeStore()  # 復帰
        r._flush()
        self.assertIn("hi", r._store.data["transcripts-m1.jsonl"])
        with open(relay._queue_path(), encoding="utf-8") as f:
            self.assertEqual(f.read(), "")


class FirstRunSkipTest(_Base):
    def _home_with_pi_cursor(self, cursor_ts):
        home = tempfile.mkdtemp()
        with open(os.path.join(home, "cursors.json"), "w", encoding="utf-8") as f:
            json.dump({"transcripts_pi": cursor_ts}, f)
        return home

    def test_old_dreamed_file_skipped(self):
        home = self._home_with_pi_cursor(fmt_ts(now_utc()))  # カーソル=今
        p = self._session("s.jsonl", [
            {"type": "session", "id": "S", "cwd": "/p", "timestamp": "2026-01-01T00:00:00.000Z"},
            {"type": "message", "id": "a", "timestamp": "2026-01-01T00:00:01.000Z",
             "message": {"role": "user", "content": "old"}},
        ])
        old = now_utc().timestamp() - 3600
        os.utime(p, (old, old))  # mtime をカーソルより古く＝夢見済み
        r = relay.Relay(self.pi_store, "m1", home=home)
        try:
            self.assertEqual(r._extract_new(), [])
        finally:
            shutil.rmtree(home)

    def test_recent_file_not_skipped(self):
        home = self._home_with_pi_cursor("2026-01-01T00:00:00.000Z")  # 古いカーソル
        self._session("s.jsonl", [
            {"type": "session", "id": "S", "cwd": "/p", "timestamp": fmt_ts(now_utc())},
            {"type": "message", "id": "a", "timestamp": fmt_ts(now_utc()),
             "message": {"role": "user", "content": "fresh"}},
        ])
        r = relay.Relay(self.pi_store, "m1", home=home)
        try:
            self.assertEqual(len(r._extract_new()), 1)
        finally:
            shutil.rmtree(home)


class StartTest(_Base):
    def test_start_noop_when_unauthorized(self):
        saved = cloud.get_store
        cloud.get_store = lambda: None
        try:
            r = relay.Relay(self.pi_store, "m1")
            r.start()
            self.assertIsNone(r._thread)
        finally:
            cloud.get_store = saved


if __name__ == "__main__":
    unittest.main()
