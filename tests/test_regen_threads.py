"""open_threads の3層フェード（active / dormant / sunk）+ 項目ごとの deadline の契約テスト。

- fold_life は log を読まない純関数（rows, now を受ける）なので、しきい値の判定は直接検証する。
- 決定論（state = f(log, now)）と audit の乖離検査は、一時 WATARI_HOME に log を置いて確かめる。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import timedelta

from watari_cli.engine import audit, regen_state, watari_lib as wl
from watari_cli.engine.watari_lib import DORMANT_DAYS, SINK_DAYS, fmt_ts, parse_ts

NOW = parse_ts("2026-07-18T00:00:00.000Z")


def _ago(days: float) -> str:
    return fmt_ts(NOW - timedelta(days=days))


def _future(days: float) -> str:
    return fmt_ts(NOW + timedelta(days=days))


def thread_row(topic, days_ago, uuid, *, status=None, note="n", deadline=None):
    d = {"ts": _ago(days_ago), "kind": "thread", "topic": topic,
         "summary": "s", "note": note, "refs": {"uuid": uuid}}
    if status:
        d["status"] = status
    if deadline:
        d["deadline"] = deadline
    return d


def fold_threads(rows, now=NOW):
    """fold_life の open_threads 出力を {topic: dict} で返す。"""
    _profile, _interests, threads = regen_state.fold_life(rows, now)
    return {t["topic"]: t for t in threads}


class ThreeTierFadeTest(unittest.TestCase):
    def test_active_has_no_dormant_flag(self):
        threads = fold_threads([thread_row("a", 10, "u1")])
        self.assertIn("a", threads)
        self.assertNotIn("dormant", threads["a"])
        self.assertNotIn("dormant_days", threads["a"])

    def test_dormant_stays_in_state_with_flag_and_days(self):
        threads = fold_threads([thread_row("a", 60, "u1")])
        self.assertIn("a", threads)  # dormant はまだ open_threads に載る
        self.assertTrue(threads["a"]["dormant"])
        self.assertEqual(threads["a"]["dormant_days"], 60)

    def test_dormant_lower_boundary_is_inclusive(self):
        # age == DORMANT_DAYS はちょうど dormant 入り
        threads = fold_threads([thread_row("a", DORMANT_DAYS, "u1")])
        self.assertTrue(threads["a"]["dormant"])

    def test_just_below_dormant_is_active(self):
        threads = fold_threads([thread_row("a", DORMANT_DAYS - 1, "u1")])
        self.assertNotIn("dormant", threads["a"])

    def test_sunk_is_excluded(self):
        threads = fold_threads([thread_row("a", 100, "u1")])
        self.assertNotIn("a", threads)

    def test_sink_boundary_is_inclusive(self):
        # age == SINK_DAYS で沈む（state から外れる）
        self.assertNotIn("a", fold_threads([thread_row("a", SINK_DAYS, "u1")]))
        # その1日手前はまだ dormant として残る
        self.assertTrue(fold_threads([thread_row("a", SINK_DAYS - 1, "u1")])["a"]["dormant"])

    def test_closed_excluded_even_when_recent(self):
        threads = fold_threads([thread_row("a", 1, "u1", status="closed")])
        self.assertNotIn("a", threads)

    def test_future_deadline_keeps_active_past_sink(self):
        # 100日更新なし（本来 sunk）でも deadline が未来なら active 固定
        threads = fold_threads([thread_row("a", 100, "u1", deadline=_future(30))])
        self.assertIn("a", threads)
        self.assertNotIn("dormant", threads["a"])
        self.assertEqual(threads["a"]["deadline"], _future(30))

    def test_future_deadline_overrides_dormant(self):
        threads = fold_threads([thread_row("a", 60, "u1", deadline=_future(5))])
        self.assertNotIn("dormant", threads["a"])

    def test_past_deadline_falls_back_to_age(self):
        # deadline が過去なら age 規則に戻る（60日 → dormant）
        threads = fold_threads([thread_row("a", 60, "u1", deadline=_ago(5))])
        self.assertTrue(threads["a"]["dormant"])
        self.assertEqual(threads["a"]["deadline"], _ago(5))

    def test_active_thread_carries_deadline_in_output(self):
        threads = fold_threads([thread_row("a", 10, "u1", deadline=_future(30))])
        self.assertEqual(threads["a"]["deadline"], _future(30))

    def test_latest_non_null_deadline_wins(self):
        rows = [
            thread_row("a", 20, "u1", deadline=_future(10)),  # 古い
            thread_row("a", 10, "u2", deadline=_future(40)),  # 新しい
        ]
        self.assertEqual(fold_threads(rows)["a"]["deadline"], _future(40))

    def test_later_null_deadline_does_not_clear(self):
        rows = [
            thread_row("a", 20, "u1", deadline=_future(10)),
            thread_row("a", 10, "u2"),  # deadline なし → 直前の値を保持
        ]
        self.assertEqual(fold_threads(rows)["a"]["deadline"], _future(10))


class RegenDeterminismAuditTest(unittest.TestCase):
    """一時 WATARI_HOME に log を置き、state = f(log, now) と audit の一貫性を確かめる。"""

    def setUp(self):
        self._saved_mem = wl.MEM
        self._tmp = tempfile.TemporaryDirectory(prefix="watari-threads-")
        home = self._tmp.name
        wl.MEM = home
        for sub in ("life", "learning"):
            os.makedirs(os.path.join(home, sub), exist_ok=True)
            open(wl.log_path(sub), "w", encoding="utf-8").close()
        rows = [
            thread_row("active-topic", 5, "u-active"),
            thread_row("dormant-topic", 60, "u-dormant"),
            thread_row("sunk-topic", 120, "u-sunk"),
            thread_row("deadline-topic", 100, "u-deadline", deadline=_future(30)),
        ]
        with open(wl.log_path("life"), "w", encoding="utf-8") as f:
            for d in rows:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        # log から state を作って書き出す（clone 直後の復元と同じ経路）
        for genre, out in regen_state.regen(NOW).items():
            wl.atomic_write_json(wl.state_path(genre), out)

    def tearDown(self):
        wl.MEM = self._saved_mem
        self._tmp.cleanup()

    def test_open_threads_tiers_land_in_state(self):
        life = json.load(open(wl.state_path("life"), encoding="utf-8"))
        by_topic = {t["topic"]: t for t in life["open_threads"]}
        self.assertIn("active-topic", by_topic)
        self.assertNotIn("dormant", by_topic["active-topic"])
        self.assertTrue(by_topic["dormant-topic"]["dormant"])
        self.assertEqual(by_topic["dormant-topic"]["dormant_days"], 60)
        self.assertNotIn("sunk-topic", by_topic)  # 沈んだ
        self.assertIn("deadline-topic", by_topic)  # 期限が未来なので残る
        self.assertNotIn("dormant", by_topic["deadline-topic"])

    def test_state_is_deterministic_function_of_log_and_now(self):
        self.assertEqual(regen_state.regen(NOW), regen_state.regen(NOW))

    def test_audit_state_derivation_stays_consistent(self):
        # state を log から作ったので乖離は0件（決定論が保たれている）
        self.assertEqual(audit.check_state_derivation(), [])

    def test_audit_references_handles_new_fields(self):
        infos = audit.check_references(NOW)
        self.assertIsInstance(infos, list)
        # deadline が未来の thread は「まもなく沈む」に挙げない
        self.assertFalse(any("deadline-topic" in x for x in infos))


if __name__ == "__main__":
    unittest.main()
