"""能動ブリーフィングは記憶と接続サービスの実状態だけから決定論で作る。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from watari_cli import briefing

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]
PI_EXTENSION = ROOT / "src" / "watari_cli" / "pi" / "briefing.ts"


class MemoryBriefingTest(unittest.TestCase):
    def test_deadlines_and_dormant_threads_become_ranked_signals(self):
        life = {
            "open_threads": [
                {"topic": "期限切れ", "note": "未完了", "last": "2026-07-20T00:00:00Z",
                 "deadline": "2026-07-22T12:00:00Z"},
                {"topic": "明日", "note": "提出", "last": "2026-07-20T00:00:00Z",
                 "deadline": "2026-07-24T12:00:00Z"},
                {"topic": "休眠", "note": "進行状況を確認", "last": "2026-05-01T00:00:00Z",
                 "dormant": True, "dormant_days": 83},
            ]
        }
        signals = briefing.memory_signals(life, NOW)
        self.assertEqual([s["title"] for s in signals], ["期限切れ", "明日", "休眠"])
        self.assertEqual([s["urgency"] for s in signals], [3, 3, 1])
        self.assertEqual(signals[0]["kind"], "deadline")
        self.assertEqual(signals[2]["kind"], "dormant")

    def test_active_thread_without_deadline_is_not_guessed_as_forgotten(self):
        life = {"open_threads": [{"topic": "進行中", "note": "作業中", "last": "2026-07-22T00:00:00Z"}]}
        self.assertEqual(briefing.memory_signals(life, NOW), [])


class DeliveryCooldownTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "briefing.json")
        self.signal = {
            "id": "calendar:event-1", "kind": "event", "source": "calendar",
            "urgency": 2, "title": "打ち合わせ", "reason": "24時間以内です",
            "due_at": "2026-07-24T09:00:00Z", "pointer": "https://example.test/event-1",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_marked_signal_is_suppressed_until_fingerprint_changes(self):
        first = briefing.filter_delivery([self.signal], NOW, self.path, mark=True)
        self.assertEqual(first, [self.signal])
        second = briefing.filter_delivery([self.signal], NOW, self.path, mark=True)
        self.assertEqual(second, [])
        changed = {**self.signal, "urgency": 3, "reason": "2時間以内です"}
        self.assertEqual(briefing.filter_delivery([changed], NOW, self.path, mark=True), [changed])
        state = json.load(open(self.path, encoding="utf-8"))
        self.assertEqual(list(state), ["shown"])
        self.assertNotIn("title", json.dumps(state, ensure_ascii=False))


class DeliveryLimitTest(unittest.TestCase):
    def test_only_displayed_signals_are_marked_shown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "briefing.json")
            signals = [
                {"id": f"signal-{i}", "kind": "deadline", "source": "memory",
                 "urgency": 3, "title": f"確認{i}", "reason": "期限です",
                 "due_at": f"2026-07-{20 + i:02d}T00:00:00Z", "pointer": None}
                for i in range(1, 5)
            ]
            shown = briefing.select_for_delivery(signals, NOW, limit=3, path=path, mark=True)
            self.assertEqual([row["id"] for row in shown], ["signal-1", "signal-2", "signal-3"])
            remaining = briefing.select_for_delivery(signals, NOW, limit=3, path=path, mark=False)
            self.assertEqual([row["id"] for row in remaining], ["signal-4"])

    def test_manual_delivery_ignores_automatic_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "briefing.json")
            briefing.select_for_delivery([self_signal := {
                "id": "signal-1", "kind": "deadline", "source": "memory",
                "urgency": 3, "title": "確認", "reason": "期限です",
                "due_at": "2026-07-23T12:00:00Z", "pointer": None,
            }], NOW, limit=3, path=path, mark=True)
            manual = briefing.select_for_delivery(
                [self_signal], NOW, limit=3, path=path, mark=False, suppress_recent=False)
            self.assertEqual(manual, [self_signal])


class RankingTest(unittest.TestCase):
    def test_urgency_then_due_time_is_stable(self):
        rows = [
            {"id": "b", "urgency": 2, "due_at": "2026-07-25T00:00:00Z"},
            {"id": "c", "urgency": 3, "due_at": None},
            {"id": "a", "urgency": 2, "due_at": "2026-07-24T00:00:00Z"},
        ]
        self.assertEqual([x["id"] for x in briefing.rank_signals(rows)], ["c", "a", "b"])


class PiBriefingBoundaryTest(unittest.TestCase):
    def test_confirmation_items_are_tui_only_and_legacy_messages_are_filtered(self):
        text = PI_EXTENSION.read_text(encoding="utf-8")
        self.assertIn('pi.registerEntryRenderer("watari-briefing"', text)
        self.assertIn('pi.appendEntry("watari-briefing"', text)
        self.assertIn('pi.on("context"', text)
        self.assertNotIn("pi.registerMessageRenderer", text)
        self.assertNotIn("pi.sendMessage", text)


if __name__ == "__main__":
    unittest.main()
