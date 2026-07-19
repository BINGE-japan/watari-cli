"""夢の共有ストリーム読み口＋クラウド削除の契約テスト（cloud store はフェイク）。

- scan_cloud_stream: 他マシンの発話を読み、自分は skip、cursor で絞り、uuid=pi:<machine>:<turn_id>。
- run(): cloud ソースが stores/messages に載る。
- ingest --advance-cloud: cloud_<machine> カーソルを host record に前進。
- prune_cloud: 全マシンが夢に見た分＋days 超を削除、未読があれば days 保険のみ。
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from datetime import timedelta

from watari_cli import cloud, host, relay
from watari_cli.engine import extract, ingest, watari_lib as wl
from watari_cli.engine.watari_lib import fmt_ts, now_utc


def _line(ts, tid, machine, role, text, cwd="/w"):
    return json.dumps({"ts": ts, "turn_id": tid, "machine": machine,
                       "cwd": cwd, "role": role, "text": text}, ensure_ascii=False) + "\n"


class FakeStore(cloud.CloudStore):
    def __init__(self):
        self.files_data: dict = {}

    def list(self):
        return [{"name": n} for n in self.files_data]

    def read(self, name):
        return self.files_data.get(name, "")

    def write(self, name, text):
        self.files_data[name] = text

    def append(self, name, text):
        self.files_data[name] = self.files_data.get(name, "") + text

    def delete(self, name):
        self.files_data.pop(name, None)


class _Cloud(unittest.TestCase):
    def setUp(self):
        self._saved = cloud.get_store
        self.store = FakeStore()
        cloud.get_store = lambda: self.store

    def tearDown(self):
        cloud.get_store = self._saved


class ScanCloudTest(_Cloud):
    def test_reads_others_skips_self(self):
        self.store.files_data["transcripts-A.jsonl"] = (
            _line("2026-07-19T00:00:01.000Z", "t1", "A", "user", "hi from A")
            + _line("2026-07-19T00:00:02.000Z", "t2", "A", "assistant", "reply"))
        self.store.files_data["transcripts-me.jsonl"] = _line(
            "2026-07-19T00:00:03.000Z", "t3", "me", "user", "own")
        sources = extract.scan_cloud_stream({}, "me")
        self.assertEqual(len(sources), 1)
        skey, ckey, readable, msgs = sources[0]
        self.assertEqual((skey, ckey, readable), ("cloud_A", "cloud_A", True))
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["uuid"], "pi:A:t1")
        self.assertEqual(msgs[0]["role"], "user")

    def test_cursor_filters(self):
        self.store.files_data["transcripts-A.jsonl"] = (
            _line("2026-07-19T00:00:01.000Z", "t1", "A", "user", "old")
            + _line("2026-07-19T00:00:05.000Z", "t2", "A", "user", "new"))
        _, _, _, msgs = extract.scan_cloud_stream({"cloud_A": "2026-07-19T00:00:01.000Z"}, "me")[0]
        self.assertEqual([m["uuid"] for m in msgs], ["pi:A:t2"])

    def test_unauthorized_empty(self):
        cloud.get_store = lambda: None
        self.assertEqual(extract.scan_cloud_stream({}, "me"), [])


class RunWithCloudTest(_Cloud):
    def test_run_includes_cloud(self):
        self.store.files_data["transcripts-A.jsonl"] = _line(
            "2026-07-19T00:00:01.000Z", "t1", "A", "user", "hi")
        pi = tempfile.mkdtemp()
        home = tempfile.mkdtemp()
        saved = (extract.PI_STORE, wl.MEM)
        extract.PI_STORE, wl.MEM = pi, home
        try:
            result = extract.run()
        finally:
            extract.PI_STORE, wl.MEM = saved
            shutil.rmtree(pi); shutil.rmtree(home)
        self.assertIn("cloud_A", result["stores"])
        self.assertTrue(any(m["uuid"] == "pi:A:t1" for m in result["messages"]))


class IngestCloudCursorTest(unittest.TestCase):
    def setUp(self):
        self._saved = (wl.MEM, ingest.MEM)
        self._tmp = tempfile.TemporaryDirectory(prefix="watari-ic-")
        home = self._tmp.name
        wl.MEM = ingest.MEM = home
        for sub in ("life", "learning"):
            os.makedirs(os.path.join(home, sub))
            open(wl.log_path(sub), "w", encoding="utf-8").close()

    def tearDown(self):
        wl.MEM, ingest.MEM = self._saved
        self._tmp.cleanup()

    def test_advance_cloud_lands_in_host_record(self):
        row = {"kind": "thread", "topic": "t", "summary": "s", "note": "n",
               "ts": "2026-07-19T00:00:00.000Z", "refs": {"uuid": "u1"}}
        ingest.apply([row], advance_cloud=["A=2026-07-19T00:00:05.000Z"])
        rec = json.load(open(host.host_path(wl.MEM), encoding="utf-8"))
        self.assertEqual(rec["cursors"]["cloud_A"], "2026-07-19T00:00:05.000Z")

    def test_advance_cloud_bad_form_rejected(self):
        row = {"kind": "thread", "topic": "t", "summary": "s", "note": "n",
               "ts": "2026-07-19T00:00:00.000Z", "refs": {"uuid": "u1"}}
        with self.assertRaises(ValueError):
            ingest.apply([row], advance_cloud=["A-no-eq"])


class PruneCloudTest(_Cloud):
    def _home_with_hosts(self, hosts):
        home = tempfile.mkdtemp()
        os.makedirs(os.path.join(home, "hosts"))
        for mid, curs in hosts.items():
            with open(os.path.join(home, "hosts", f"{mid}.json"), "w", encoding="utf-8") as f:
                json.dump({"machine_id": mid, "cursors": curs}, f)
        return home

    def test_deletes_all_dreamed_keeps_rest(self):
        home = self._home_with_hosts({
            "B": {"cloud_A": "2026-07-19T00:00:03.000Z"},
            "C": {"cloud_A": "2026-07-19T00:00:05.000Z"}})  # min(B,C)=03
        self.store.files_data["transcripts-A.jsonl"] = (
            _line("2026-07-19T00:00:01.000Z", "t1", "A", "user", "dreamed")
            + _line("2026-07-19T00:00:04.000Z", "t2", "A", "user", "notyet"))
        try:
            relay.prune_cloud(home, days=90)  # エントリは当日＝保険は効かず、dreamed だけ検証
        finally:
            kept = self.store.files_data["transcripts-A.jsonl"]
            shutil.rmtree(home)
        self.assertNotIn("dreamed", kept)
        self.assertIn("notyet", kept)

    def test_90day_cap_when_not_all_dreamed(self):
        home = self._home_with_hosts({"B": {}})  # B は未読 → min なし → 保険のみ
        self.store.files_data["transcripts-A.jsonl"] = (
            _line(fmt_ts(now_utc() - timedelta(days=100)), "t1", "A", "user", "ancient")
            + _line(fmt_ts(now_utc() - timedelta(days=1)), "t2", "A", "user", "fresh"))
        try:
            relay.prune_cloud(home, days=90)
        finally:
            kept = self.store.files_data["transcripts-A.jsonl"]
            shutil.rmtree(home)
        self.assertNotIn("ancient", kept)
        self.assertIn("fresh", kept)


if __name__ == "__main__":
    unittest.main()
