"""エンジンの決定論コアの移植パリティ + 意図的変更の契約テスト。

既存の test_regen_threads.py（open_threads の3層フェード）と test_host.py（カーソルの
host 記録化）を補い、決定論コアで直接の被覆が無かった箇所を固める:
- extract: 本物発話の選別 / Codex 合成 uuid / カーソル絞り込み / 窓トランケート
- ingest : (uuid,kind) 重複スキップ / 検証の原子性 / カーソル後退拒否 / deadline 検証 / 不正JSON
- regen  : learning 畳み込み（mastery 非降格・freshness・related 和集合・alias）/ interests 減衰

注: watari_lib.MEM はモジュール定数（import 時に env から一度だけ解決）。ingest は MEM を
「値で」import するため、一時 home へ向けるには wl.MEM と ingest.MEM の両方を差し替える。
extract は STORES/CODEX_STORE を値で持つので、そちらを差し替える。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import timedelta

from watari_cli import host
from watari_cli.engine import extract, ingest, regen_state, watari_lib as wl
from watari_cli.engine.watari_lib import fmt_ts, parse_ts


def _write_jsonl(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class ExtractSelectionTest(unittest.TestCase):
    """本物の binge 発話の選別・カーソル絞り込み・Codex 合成の契約。"""

    def test_scan_store_selects_only_genuine_user_messages(self):
        with tempfile.TemporaryDirectory(prefix="watari-ex-") as root:
            _write_jsonl(os.path.join(root, "proj", "sess.jsonl"), [
                {"type": "user", "timestamp": "2026-07-10T00:00:00.000Z", "uuid": "u1",
                 "cwd": "/home/binge/proj", "sessionId": "S1",
                 "message": {"content": "本物の発話"}},
                # ハーネス合成行は除外
                {"type": "user", "timestamp": "2026-07-10T00:01:00.000Z", "uuid": "u2",
                 "message": {"content": "<command-name>/watari</command-name>"}},
                # sidechain は除外
                {"type": "user", "timestamp": "2026-07-10T00:02:00.000Z", "uuid": "u3",
                 "isSidechain": True, "message": {"content": "x"}},
                # toolUseResult は除外
                {"type": "user", "timestamp": "2026-07-10T00:03:00.000Z", "uuid": "u4",
                 "toolUseResult": {}, "message": {"content": "x"}},
                # assistant は除外
                {"type": "assistant", "timestamp": "2026-07-10T00:04:00.000Z",
                 "message": {"content": "返答"}},
            ])
            ok, msgs = extract.scan_store(root, None)
            self.assertTrue(ok)
            self.assertEqual([m["uuid"] for m in msgs], ["u1"])
            self.assertEqual(msgs[0]["text"], "本物の発話")
            self.assertEqual(msgs[0]["session"], "S1")
            self.assertEqual(msgs[0]["cwd"], "/home/binge/proj")

    def test_scan_store_excludes_at_or_before_cursor(self):
        with tempfile.TemporaryDirectory(prefix="watari-ex-") as root:
            _write_jsonl(os.path.join(root, "proj", "sess.jsonl"), [
                {"type": "user", "timestamp": "2026-07-10T00:00:00.000Z", "uuid": "old",
                 "message": {"content": "old"}},
                {"type": "user", "timestamp": "2026-07-10T00:05:00.000Z", "uuid": "new",
                 "message": {"content": "new"}},
            ])
            # ts == cursor は除外・以降のみ（カーソルは「処理済みの最後」の意味）
            ok, msgs = extract.scan_store(root, "2026-07-10T00:00:00.000Z")
            self.assertTrue(ok)
            self.assertEqual([m["uuid"] for m in msgs], ["new"])

    def test_scan_store_missing_root_is_unreadable(self):
        ok, msgs = extract.scan_store("/no/such/dir", None)
        self.assertFalse(ok)
        self.assertEqual(msgs, [])

    def test_scan_codex_synthesizes_uuid_and_reads_meta(self):
        with tempfile.TemporaryDirectory(prefix="watari-cx-") as root:
            _write_jsonl(os.path.join(root, "2026", "07", "10", "rollout-abc.jsonl"), [
                {"type": "session_meta", "payload": {"id": "CX1", "cwd": "/work"}},
                {"type": "event_msg", "timestamp": "2026-07-10T00:00:00.000Z",
                 "payload": {"type": "user_message", "message": "コーデックス発話"}},
                # agent_message は除外
                {"type": "event_msg", "timestamp": "2026-07-10T00:01:00.000Z",
                 "payload": {"type": "agent_message", "message": "応答"}},
            ])
            ok, msgs = extract.scan_codex_store(root, None)
            self.assertTrue(ok)
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0]["uuid"], "codex:CX1:2026-07-10T00:00:00.000Z")
            self.assertEqual(msgs[0]["session"], "CX1")
            self.assertEqual(msgs[0]["cwd"], "/work")
            self.assertEqual(msgs[0]["text"], "コーデックス発話")

    def test_run_truncates_window_from_oldest_message(self):
        # 窓の起点は「最古の未処理メッセージ」。起点 +30日を超える発話は落とし truncated:true。
        with tempfile.TemporaryDirectory(prefix="watari-win-") as win, \
                tempfile.TemporaryDirectory(prefix="watari-wsl-") as wsl, \
                tempfile.TemporaryDirectory(prefix="watari-cx-") as codex, \
                tempfile.TemporaryDirectory(prefix="watari-home-") as home:
            _write_jsonl(os.path.join(win, "proj", "s.jsonl"), [
                {"type": "user", "timestamp": "2026-01-01T00:00:00.000Z", "uuid": "a",
                 "message": {"content": "oldest"}},
                {"type": "user", "timestamp": "2026-01-16T00:00:00.000Z", "uuid": "b",
                 "message": {"content": "within"}},
                {"type": "user", "timestamp": "2026-02-20T00:00:00.000Z", "uuid": "c",
                 "message": {"content": "beyond-window"}},
            ])
            saved = (extract.STORES, extract.CODEX_STORE, wl.MEM)
            extract.STORES = {"win": win, "wsl": wsl}
            extract.CODEX_STORE = codex
            wl.MEM = home  # 空 home → カーソルは全 None（絞り込み無し・書き込み無し）
            try:
                result = extract.run()
            finally:
                extract.STORES, extract.CODEX_STORE, wl.MEM = saved
            win_stats = result["stores"]["win"]
            self.assertTrue(win_stats["truncated"])
            self.assertEqual(win_stats["count"], 2)
            self.assertEqual(win_stats["max_ts"], "2026-01-16T00:00:00.000Z")
            self.assertEqual([m["uuid"] for m in result["messages"]], ["a", "b"])


class IngestApplyTest(unittest.TestCase):
    """検証→dedup→追記→カーソル前進→state 再生成 の契約。カーソルは host 記録に載る。"""

    def setUp(self):
        self._saved = (wl.MEM, ingest.MEM)
        self._tmp = tempfile.TemporaryDirectory(prefix="watari-ing-")
        home = self._tmp.name
        wl.MEM = home
        ingest.MEM = home  # ingest は MEM を値で import するため差し替える
        for sub in ("life", "learning"):
            os.makedirs(os.path.join(home, sub), exist_ok=True)
            open(wl.log_path(sub), "w", encoding="utf-8").close()
        self.home = home

    def tearDown(self):
        wl.MEM, ingest.MEM = self._saved
        self._tmp.cleanup()

    def _row(self, uuid="u1", **kw):
        d = {"kind": "thread", "topic": "t", "summary": "s", "note": "n",
             "ts": "2026-07-10T00:00:00.000Z", "refs": {"uuid": uuid}}
        d.update(kw)
        return d

    def test_dedup_by_uuid_and_kind(self):
        s1 = ingest.apply([self._row()])
        self.assertIn("life=1", s1)
        s2 = ingest.apply([self._row()])  # 同 (uuid,kind) は黙ってスキップ
        self.assertIn("dedupスキップ=1", s2)
        self.assertIn("life=0", s2)
        self.assertEqual(len(wl.load_log("life")), 1)

    def test_validation_error_writes_nothing(self):
        with self.assertRaises(ValueError):
            ingest.apply([self._row(uuid="")])  # refs.uuid 欠落 → 検証失敗
        self.assertEqual(wl.load_log("life"), [])            # log は無傷
        self.assertFalse(os.path.exists(host.host_path(self.home)))  # host 記録も書かない

    def test_cursor_backward_rejected_and_atomic(self):
        ingest.apply([self._row(uuid="u1")], advance_wsl="2026-07-10T00:00:00.000Z")
        with self.assertRaises(ValueError) as cm:
            ingest.apply([self._row(uuid="u2")], advance_wsl="2026-07-01T00:00:00.000Z")
        self.assertTrue(any("後退禁止" in e for e in cm.exception.args[0]))
        # 後退拒否で u2 は書かれない（原子性）
        self.assertEqual([d["refs"]["uuid"] for d in wl.load_log("life")], ["u1"])

    def test_cursor_advance_lands_in_host_record_not_shared_json(self):
        ingest.apply([self._row(uuid="u1")], advance_wsl="2026-07-10T00:00:00.000Z")
        record = json.load(open(host.host_path(self.home), encoding="utf-8"))
        self.assertEqual(record["cursors"]["transcripts_wsl"], "2026-07-10T00:00:00.000Z")
        self.assertIn("last_run", record["cursors"])
        # 共有 cursors.json は（このマシンからは）作らない
        self.assertFalse(os.path.exists(os.path.join(self.home, "cursors.json")))

    def test_dry_run_does_not_append(self):
        summary = ingest.apply([self._row(uuid="u1")], dry_run=True)
        self.assertIn("dry-run", summary)
        self.assertEqual(wl.load_log("life"), [])

    def test_deadline_must_be_tz_aware(self):
        with self.assertRaises(ValueError) as cm:
            ingest.apply([self._row(uuid="u1", deadline="2026-09-01T00:00:00")])  # naive
        self.assertTrue(any("deadline" in e for e in cm.exception.args[0]))

    def test_valid_deadline_accepted_and_stored_in_log(self):
        ingest.apply([self._row(uuid="u1", deadline="2026-12-01T00:00:00.000Z")])
        self.assertEqual(wl.load_log("life")[0]["deadline"], "2026-12-01T00:00:00.000Z")


class LoadRowsTest(unittest.TestCase):
    """rows ファイルの読み込みは、常に「エラー文字列のリスト」を持つ ValueError で失敗する。"""

    def test_malformed_json_raises_list_valueerror(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("not json{{{")
            path = f.name
        try:
            with self.assertRaises(ValueError) as cm:
                ingest.load_rows(path)
        finally:
            os.unlink(path)
        errors = cm.exception.args[0]
        self.assertIsInstance(errors, list)   # 1文字ずつ列挙されない（回帰防止）
        self.assertEqual(len(errors), 1)
        self.assertIn("不正な JSON", errors[0])

    def test_non_list_json_raises(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write('{"kind": "thread"}')
            path = f.name
        try:
            with self.assertRaises(ValueError) as cm:
                ingest.load_rows(path)
        finally:
            os.unlink(path)
        self.assertEqual(cm.exception.args[0], ["rows は JSON 配列"])


class FoldLearningTest(unittest.TestCase):
    """learning 畳み込み（純関数）の規則。"""

    def _study(self, topic, ts, uuid, **kw):
        d = {"kind": "study", "domain": "python", "topic": topic, "summary": "s",
             "note": "n", "mastery": 1, "ts": ts, "refs": {"uuid": uuid}}
        d.update(kw)
        return d

    def test_mastery_takes_max_never_downgrades(self):
        rows = [self._study("t", "2026-07-01T00:00:00.000Z", "u1", mastery=3),
                self._study("t", "2026-07-02T00:00:00.000Z", "u2", mastery=1)]
        t = regen_state.fold_learning(rows, {})["python"]["topics"]["t"]
        self.assertEqual(t["mastery"], 3)

    def test_freshness_takes_max_of_freshness_or_ts(self):
        rows = [self._study("t", "2026-07-01T00:00:00.000Z", "u1",
                             freshness="2026-08-01T00:00:00.000Z"),
                self._study("t", "2026-07-05T00:00:00.000Z", "u2")]
        t = regen_state.fold_learning(rows, {})["python"]["topics"]["t"]
        self.assertEqual(t["freshness"], "2026-08-01T00:00:00.000Z")
        self.assertEqual(t["last"], "2026-07-05T00:00:00.000Z")

    def test_related_is_union_in_first_seen_order_without_self_ref(self):
        rows = [self._study("t", "2026-07-01T00:00:00.000Z", "u1",
                             related=["python/t", "python/other", "go/x"]),
                self._study("t", "2026-07-02T00:00:00.000Z", "u2",
                             related=["go/x", "rust/y"])]
        t = regen_state.fold_learning(rows, {})["python"]["topics"]["t"]
        self.assertEqual(t["related"], ["python/other", "go/x", "rust/y"])

    def test_alias_folds_domain(self):
        rows = [self._study("t", "2026-07-01T00:00:00.000Z", "u1")]
        domains = regen_state.fold_learning(rows, {"python": "py3"})
        self.assertIn("py3", domains)
        self.assertNotIn("python", domains)

    def test_note_falls_back_to_summary(self):
        row = self._study("t", "2026-07-01T00:00:00.000Z", "u1")
        row.pop("note")
        row["summary"] = "サマリ"
        t = regen_state.fold_learning([row], {})["python"]["topics"]["t"]
        self.assertEqual(t["note"], "サマリ")


class FoldInterestsTest(unittest.TestCase):
    """interests の heat 減衰（30日で1下がり・0で state から落ちる）。"""

    def _interest(self, ts, uuid, **kw):
        d = {"kind": "interest", "topic": "jazz", "summary": "s", "note": "n",
             "ts": ts, "refs": {"uuid": uuid}}
        d.update(kw)
        return d

    def test_heat_decays_one_per_30_days(self):
        now = parse_ts("2026-07-01T00:00:00.000Z")
        row = self._interest(fmt_ts(now - timedelta(days=60)), "u1", heat=3)  # decay 2 → eff 1
        _profile, interests, _threads = regen_state.fold_life([row], now)
        self.assertEqual(interests["jazz"]["heat"], 1)

    def test_interest_drops_when_effective_heat_zero(self):
        now = parse_ts("2026-07-01T00:00:00.000Z")
        row = self._interest(fmt_ts(now - timedelta(days=60)), "u1", heat=1)  # decay 2 → eff 0
        _profile, interests, _threads = regen_state.fold_life([row], now)
        self.assertNotIn("jazz", interests)


if __name__ == "__main__":
    unittest.main()
