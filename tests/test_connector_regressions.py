"""Fable レビューで見つかった実運用バグの回帰テスト（Pi 側からの不具合報告に対応）。

- Chatwork: 新着なしの 204 No Content を失敗にしない
- GitHub: ミリ秒付きカーソルを検索修飾子へ渡すと 422 になるので秒精度へ丸める
- Google: カーソル未設定（初回接続）は全履歴でなく直近 INITIAL_LOOKBACK_DAYS 日だけ見る
"""
import json
import os
import unittest
from datetime import timedelta

from watari_cli import chatwork, github, google_connectors as g
from watari_cli.engine.watari_lib import now_utc, parse_ts


class ChatworkNoContentTest(unittest.TestCase):
    def setUp(self):
        self._saved = chatwork._http

    def tearDown(self):
        chatwork._http = self._saved

    def test_204_is_empty_not_error(self):
        chatwork._http = lambda m, u, h=None, d=None: (204, b"")
        self.assertEqual(chatwork._get("tok", "https://api.chatwork.com/v2/rooms/1/messages"), [])


class GithubSearchTimestampTest(unittest.TestCase):
    def test_millisecond_cursor_is_truncated_to_seconds(self):
        # カーソルはミリ秒付き（log/state が書く形式）。GitHub 検索は秒までしか受けない。
        self.assertEqual(github._to_search_ts("2026-07-20T05:07:01.176Z"), "2026-07-20T05:07:01Z")
        self.assertEqual(github._to_search_ts("2026-07-20T05:07:01Z"), "2026-07-20T05:07:01Z")

    def test_query_has_no_fractional_seconds(self):
        captured = {}

        def fake_get(token, url):
            captured.setdefault("urls", []).append(url)
            if url.endswith("/user"):
                return {"login": "binge"}
            return {"items": []}

        saved = github._get
        github._get = fake_get
        try:
            github.read("tok", "2026-07-20T05:07:01.176Z")
        finally:
            github._get = saved
        search_url = [u for u in captured["urls"] if "search" in u][0]
        self.assertNotIn(".176", search_url)


class GoogleInitialWindowTest(unittest.TestCase):
    def test_default_since_is_recent_not_epoch(self):
        since = parse_ts(g._default_since())
        delta = now_utc() - since
        self.assertLess(abs(delta - timedelta(days=g.INITIAL_LOOKBACK_DAYS)), timedelta(minutes=5))

    def test_drive_first_run_uses_window(self):
        captured = {}

        def fake_get_json(service, url, token):
            captured["url"] = url
            return {"files": []}

        saved_get, saved_token = g._get_json, g.cloud.access_token
        g._get_json = fake_get_json
        g.cloud.access_token = lambda: "tok"
        try:
            g.gdrive_read(None)  # カーソル未設定＝初回
        finally:
            g._get_json, g.cloud.access_token = saved_get, saved_token
        self.assertNotIn("1970", captured["url"])


if __name__ == "__main__":
    unittest.main()
