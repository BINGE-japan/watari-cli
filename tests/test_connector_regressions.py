"""コネクタ層の回帰テスト（実運用バグ＋公開品質化の文言契約）。

- Chatwork: 新着なしの 204 No Content を失敗にしない
- GitHub: ミリ秒付きカーソルを検索修飾子へ渡すと 422 になるので秒精度へ丸める
- Google: カーソル未設定（初回接続）は全履歴でなく直近 INITIAL_LOOKBACK_DAYS 日だけ見る
- 公開品質化（DESIGN-public-ux §6）:
  - API 応答 body は UTF-8 デコードして表示（bytes repr の b'...' を出さない）
  - verify/read の失敗に英語フィールド名（viewer/login/name/user_id）を出さず、
    再接続コマンド（watari connect <name>）を必ず添える
  - Notion は verify 成功後に読めるページ数を確かめ、0 件なら注意を添える（成功のまま）
  - GitHub guide は Fine-grained 直リンク＋有効期限切れ時の再発行案内
"""
import json
import os
import unittest
from datetime import timedelta

from watari_cli import (chatwork, connector_http, connectors, github,
                        google_connectors as g, linear, notion, slack)
from watari_cli.connectors import ConnectorError
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


class BodyTextHelperTest(unittest.TestCase):
    """connector_http.body_text: bytes を UTF-8 デコードし、空白を畳んで上限で切る。"""

    def test_decodes_utf8_bytes(self):
        self.assertEqual(connector_http.body_text("エラー詳細".encode("utf-8")), "エラー詳細")

    def test_collapses_whitespace_and_truncates(self):
        text = connector_http.body_text(b'{\n  "error": "x"\n}')
        self.assertEqual(text, '{ "error": "x" }')
        self.assertEqual(len(connector_http.body_text(b"a" * 500)), 200)

    def test_invalid_bytes_do_not_crash(self):
        self.assertIn("�", connector_http.body_text(b"\xff\xfe"))


class NoBytesReprInErrorsTest(unittest.TestCase):
    """API エラー時の応答 body 表示に bytes repr（b'...'）が出ないこと（全サービス共通）。"""

    _BODY = '{"message": "サーバ側エラー"}'.encode("utf-8")

    def _assert_plain(self, exc: ConnectorError, service: str):
        message = str(exc)
        self.assertNotIn("b'", message)
        self.assertIn("サーバ側エラー", message)

    def test_linear_github_notion_slack_chatwork_google(self):
        cases = [
            (linear, lambda: linear._post("k", "{ viewer }"), "linear"),
            (github, lambda: github._get("t", "https://api.github.com/user"), "github"),
            (notion, lambda: notion._request("t", "GET", "https://api.notion.com/v1/users/me"),
             "notion"),
            (slack, lambda: slack._call("xoxp-t", "POST", slack.AUTH_TEST_URL), "slack"),
            (chatwork, lambda: chatwork._get("t", "https://api.chatwork.com/v2/me"), "chatwork"),
            (g, lambda: g._get_json("gmail", "https://gmail.googleapis.com/x", "t"), "gmail"),
        ]
        for module, call, service in cases:
            saved = module._http
            module._http = lambda m, u, h=None, d=None: (500, self._BODY)
            try:
                with self.assertRaises(ConnectorError) as cm:
                    call()
            finally:
                module._http = saved
            self._assert_plain(cm.exception, service)


class VerifyErrorWordingTest(unittest.TestCase):
    """verify の失敗文言: 英語フィールド名を出さず、再接続コマンドを添える。"""

    def test_linear_missing_account_info(self):
        saved = linear._post
        linear._post = lambda *a, **k: {"viewer": {}}
        try:
            ok, message = linear.verify("key")
        finally:
            linear._post = saved
        self.assertFalse(ok)
        self.assertNotIn("viewer", message)
        self.assertIn("watari connect linear", message)

    def test_github_missing_user_name(self):
        saved = github._get
        github._get = lambda *a, **k: {}
        try:
            ok, message = github.verify("token")
        finally:
            github._get = saved
        self.assertFalse(ok)
        self.assertNotIn("login", message)
        self.assertIn("watari connect github", message)

    def test_chatwork_missing_account_name(self):
        saved = chatwork._get
        chatwork._get = lambda *a, **k: {}
        try:
            ok, message = chatwork.verify("token")
        finally:
            chatwork._get = saved
        self.assertFalse(ok)
        self.assertNotIn("name が", message)
        self.assertIn("watari connect chatwork", message)

    def test_slack_read_missing_user_info(self):
        saved = slack._http
        slack._http = lambda m, u, h=None, d=None: (
            200, json.dumps({"ok": True, "user": "u", "team": "t"}).encode())
        try:
            with self.assertRaises(ConnectorError) as cm:
                slack.read("xoxp-token", None)
        finally:
            slack._http = saved
        self.assertNotIn("user_id", str(cm.exception))
        self.assertIn("watari connect slack", str(cm.exception))


class NotionZeroPagesWarningTest(unittest.TestCase):
    """Notion: verify 成功後に search を1回叩き、読めるページ 0 件なら成功のまま注意を添える。"""

    def setUp(self):
        self._saved = notion._http

    def tearDown(self):
        notion._http = self._saved

    def _router(self, results):
        def router(method, url, headers=None, data=None):
            if url.endswith("/users/me"):
                return 200, json.dumps(
                    {"name": "Watari", "bot": {"workspace_name": "WS"}}).encode()
            if url.endswith("/search"):
                return 200, json.dumps({"results": results}).encode()
            return 404, b"{}"
        return router

    def test_zero_pages_appends_warning_but_stays_ok(self):
        notion._http = self._router([])
        ok, message = notion.verify("secret")
        self.assertTrue(ok)
        self.assertIn("Watari（WS）", message)
        self.assertIn("まだ読めるページがありません", message)
        self.assertIn("接続", message)  # ページ右上メニュー→接続 の導線

    def test_readable_pages_present_keeps_message_clean(self):
        notion._http = self._router([{"id": "p1"}])
        ok, message = notion.verify("secret")
        self.assertTrue(ok)
        self.assertNotIn("まだ読めるページがありません", message)

    def test_search_failure_does_not_break_verify(self):
        def router(method, url, headers=None, data=None):
            if url.endswith("/users/me"):
                return 200, json.dumps({"name": "Watari"}).encode()
            return 500, b"boom"
        notion._http = router
        ok, message = notion.verify("secret")
        self.assertTrue(ok)  # 注意の判定に失敗しても verify 自体は成功のまま
        self.assertNotIn("まだ読めるページがありません", message)


class GithubGuideTest(unittest.TestCase):
    """GitHub guide: Fine-grained 作成画面への直リンク・実画面手順・有効期限切れ時の再発行案内。"""

    def test_guide_has_direct_link_screen_steps_and_expiry_note(self):
        guide = "\n".join(connectors.get_service("github").guide)
        self.assertIn("https://github.com/settings/personal-access-tokens/new", guide)
        self.assertIn("Repository access", guide)
        self.assertIn("Read-only", guide)
        self.assertIn("有効期限", guide)
        self.assertIn("watari connect github", guide)


if __name__ == "__main__":
    unittest.main()
