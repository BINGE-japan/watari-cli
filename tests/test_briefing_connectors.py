"""Briefing readers query current actionable state, not connector change cursors."""
from __future__ import annotations

import json
import unittest
import urllib.parse
from datetime import datetime, timezone

from watari_cli import google_connectors as google, linear

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)


def _response(value):
    return 200, json.dumps(value).encode()


class CalendarBriefTest(unittest.TestCase):
    def setUp(self):
        self.http = google._http
        self.token = google.cloud.access_token
        google.cloud.access_token = lambda: "token"

    def tearDown(self):
        google._http = self.http
        google.cloud.access_token = self.token

    def test_upcoming_events_are_queried_by_start_time(self):
        seen = []
        def fake(method, url, headers=None, data=None):
            seen.append(url)
            return _response({"items": [
                {"id": "soon", "summary": "面談", "status": "confirmed",
                 "start": {"dateTime": "2026-07-23T13:00:00Z"},
                 "htmlLink": "https://calendar.test/soon"},
                {"id": "later", "summary": "レビュー", "status": "confirmed",
                 "start": {"dateTime": "2026-07-26T12:00:00Z"}},
                {"id": "cancel", "summary": "中止", "status": "cancelled",
                 "start": {"dateTime": "2026-07-23T12:30:00Z"}},
            ]})
        google._http = fake
        signals = google.calendar_brief(NOW)
        self.assertEqual([s["title"] for s in signals], ["面談", "レビュー"])
        self.assertEqual([s["urgency"] for s in signals], [3, 1])
        query = urllib.parse.urlparse(seen[0]).query
        self.assertIn("timeMin=", query)
        self.assertIn("timeMax=", query)
        self.assertNotIn("updatedMin=", query)

    def test_today_all_day_event_remains_visible_after_midnight(self):
        def fake(method, url, headers=None, data=None):
            return _response({"timeZone": "Asia/Tokyo", "items": [
                {"id": "all-day", "summary": "終日イベント", "status": "confirmed",
                 "start": {"date": "2026-07-23"}},
            ]})
        google._http = fake
        signals = google.calendar_brief(NOW)
        self.assertEqual([s["title"] for s in signals], ["終日イベント"])
        self.assertEqual(signals[0]["reason"], "今日の終日予定です")


class GmailBriefTest(unittest.TestCase):
    def setUp(self):
        self.http = google._http
        self.token = google.cloud.access_token
        google.cloud.access_token = lambda: "token"

    def tearDown(self):
        google._http = self.http
        google.cloud.access_token = self.token

    def test_latest_inbound_without_later_reply_is_observed(self):
        def fake(method, url, headers=None, data=None):
            if url.endswith("/users/me/profile"):
                return _response({"emailAddress": "me@example.com"})
            if "/messages?" in url:
                return _response({"messages": [{"id": "m1", "threadId": "t1"},
                                                 {"id": "m2", "threadId": "t2"}]})
            if "/threads/t1?" in url:
                return _response({"id": "t1", "messages": [{
                    "id": "m1", "threadId": "t1", "internalDate": "1784548800000",
                    "labelIds": ["INBOX", "UNREAD"],
                    "payload": {"headers": [
                        {"name": "From", "value": "Alice <alice@example.com>"},
                        {"name": "Subject", "value": "確認のお願い"},
                        {"name": "Auto-Submitted", "value": "no"},
                    ]},
                }]})
            if "/threads/t2?" in url:
                return _response({"id": "t2", "messages": [
                    {"id": "m2", "internalDate": "1784548800000",
                     "payload": {"headers": [{"name": "From", "value": "Bob <bob@example.com>"},
                                               {"name": "Subject", "value": "日程"}]}},
                    {"id": "mine", "internalDate": "1784635200000",
                     "payload": {"headers": [{"name": "From", "value": "Me <me@example.com>"},
                                               {"name": "Subject", "value": "Re: 日程"}]}},
                ]})
            raise AssertionError(url)
        google._http = fake
        signals = google.gmail_brief(NOW)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["kind"], "awaiting-reply")
        self.assertEqual(signals[0]["title"], "確認のお願い")
        self.assertIn("その後の送信がありません", signals[0]["reason"])


class LinearBriefTest(unittest.TestCase):
    def setUp(self):
        self.http = linear._http

    def tearDown(self):
        linear._http = self.http

    def test_only_assigned_open_due_issues_become_signals(self):
        def fake(method, url, headers=None, data=None):
            return _response({"data": {"issues": {"nodes": [
                {"identifier": "GEN-1", "title": "今日まで", "url": "https://linear.test/1",
                 "dueDate": "2026-07-23", "state": {"name": "In Progress", "type": "started"}},
                {"identifier": "GEN-2", "title": "完了", "url": "https://linear.test/2",
                 "dueDate": "2026-07-23", "state": {"name": "Done", "type": "completed"}},
                {"identifier": "GEN-3", "title": "先の予定", "url": "https://linear.test/3",
                 "dueDate": "2026-08-20", "state": {"name": "Todo", "type": "unstarted"}},
            ]}}})
        linear._http = fake
        signals = linear.brief("key", NOW)
        self.assertEqual([s["title"] for s in signals], ["GEN-1 今日まで"])
        self.assertEqual(signals[0]["urgency"], 3)


if __name__ == "__main__":
    unittest.main()
