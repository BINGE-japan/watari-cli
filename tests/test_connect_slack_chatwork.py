"""Slack / Chatwork connector の契約テスト（linear/github/notion の tests/test_connect.py と同型）。

実 API は叩かず HTTP をモックしてオフライン検証する（slack._http / chatwork._http を差し替える）。
固めること:
- verify 成功/失敗（Slack は HTTP 200 でも ok:false を返しうるので、その分岐も別に固める）。
- Slack は xoxp- で始まらないトークン（特に bot 用の xoxb-）を verify 冒頭で拒否する。
- read の統一形式 {ts,uuid,text,meta} と ts 昇順。
- Slack は2クエリ（from:/mention）統合時の重複排除。
- 認証失敗は非ゼロ終了・出力なし・再接続コマンド（watari connect <name>）の案内付き。
- guide（案内文）に URL とマニフェスト文字列が含まれ、複数行要素は行ごとに分割されている。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.parse

from watari_cli import chatwork, config, connectors, host, slack
from watari_cli.cli import _build_parser
from watari_cli.engine import watari_lib as wl


def _run(argv):
    os.environ["WATARI_CONNECT_ALLOW_NO_TTY"] = "1"  # テストは非TTY実行のため許可
    args = _build_parser().parse_args(argv)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = args.func(args)
    return rc, out.getvalue(), err.getvalue()


def _fake_http(router):
    def f(method, url, headers=None, data=None):
        return router(method, url, headers, data)
    return f


class _XdgIsolated(unittest.TestCase):
    """XDG_CONFIG_HOME を一時ディレクトリへ向け、config.json（connectors_auth・connectors）を隔離する。"""

    def setUp(self):
        self._cfg = tempfile.TemporaryDirectory(prefix="watari-connect-cfg-")
        self._saved_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._cfg.name
        from watari_cli import prompts
        self._saved_prompts = {"text": prompts.text, "select": prompts.select}

    def tearDown(self):
        from watari_cli import prompts
        prompts.text = self._saved_prompts["text"]
        prompts.select = self._saved_prompts["select"]
        if self._saved_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._saved_xdg
        self._cfg.cleanup()


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------

class ConnectWizardSlackTest(_XdgIsolated):
    def setUp(self):
        super().setUp()
        self._saved_http = slack._http

    def tearDown(self):
        slack._http = self._saved_http
        super().tearDown()

    def _auth_ok(self, user="example-user", team="Example Team", token="xoxp-secret-123"):
        def router(method, url, headers, data):
            self.assertEqual(headers.get("Authorization"), f"Bearer {token}")
            if url == slack.AUTH_TEST_URL:
                self.assertEqual(method, "POST")
                return 200, json.dumps(
                    {"ok": True, "user": user, "team": team, "user_id": "U123"}).encode()
            return 404, b"{}"
        slack._http = _fake_http(router)

    def test_success_saves_auth_and_declares_connector(self):
        from watari_cli import prompts
        self._auth_ok()
        prompts.text = lambda *a, **k: "xoxp-secret-123"
        rc, out, err = _run(["connect", "slack"])
        self.assertEqual(rc, 0)
        self.assertIn("example-user@Example Team", out)
        self.assertNotIn("xoxp-secret-123", out)  # 認証情報は print しない
        self.assertNotIn("xoxp-secret-123", err)
        self.assertEqual(connectors.auth_key("slack"), "xoxp-secret-123")
        decl = config.load_connectors()
        self.assertEqual(len(decl), 1)
        self.assertEqual((decl[0]["name"], decl[0]["scope"]), ("slack", "cloud"))

    def test_verify_ok_false_is_a_failure_despite_http_200(self):
        from watari_cli import prompts
        prompts.text = lambda *a, **k: "xoxp-bad"
        slack._http = _fake_http(
            lambda m, u, h, d: (200, json.dumps(
                {"ok": False, "error": "invalid_auth"}).encode()))
        rc, out, err = _run(["connect", "slack"])
        self.assertEqual(rc, 1)
        self.assertIn("invalid_auth", err)
        self.assertIsNone(connectors.auth_key("slack"))
        self.assertEqual(config.load_connectors(), [])

    def test_verify_http_error_is_a_failure(self):
        from watari_cli import prompts
        prompts.text = lambda *a, **k: "xoxp-bad"
        slack._http = _fake_http(lambda m, u, h, d: (401, b'{"error":"invalid_auth"}'))
        rc, out, err = _run(["connect", "slack"])
        self.assertEqual(rc, 1)
        self.assertIsNone(connectors.auth_key("slack"))
        self.assertEqual(config.load_connectors(), [])

    def test_empty_key_aborts_without_saving(self):
        from watari_cli import prompts
        prompts.text = lambda *a, **k: ""
        rc, _out, err = _run(["connect", "slack"])
        self.assertEqual(rc, 1)
        self.assertIsNone(connectors.auth_key("slack"))
        self.assertEqual(config.load_connectors(), [])

    def test_bot_token_xoxb_is_rejected_before_any_api_call(self):
        """guide が最も警告する貼り間違い（xoxb-）は verify 冒頭で拒否し、正しい方を案内する。"""
        from watari_cli import prompts
        prompts.text = lambda *a, **k: "xoxb-bot-token-123"
        slack._http = _fake_http(
            lambda m, u, h, d: self.fail("接頭辞チェックで拒否すべき（API を叩かない）"))
        rc, _out, err = _run(["connect", "slack"])
        self.assertEqual(rc, 1)
        self.assertIn("xoxp-", err)  # 正しいトークンの見分け方を案内
        self.assertIn("bot", err)
        self.assertIsNone(connectors.auth_key("slack"))
        self.assertEqual(config.load_connectors(), [])

    def test_guide_manifest_is_split_into_single_lines(self):
        """複数行のマニフェストは guide 内で1行ずつに分割されている（表示側が各行に
        プレフィックスを付けても崩れない）。"""
        service = connectors.get_service("slack")
        self.assertTrue(all("\n" not in line for line in service.guide))
        joined = "\n".join(line.strip() for line in service.guide)
        self.assertIn('"search:read"', joined)

    def test_guide_mentions_apps_url_and_manifest(self):
        from watari_cli import prompts
        prompts.text = lambda *a, **k: ""  # 空入力で中止させ、案内文だけを見る
        rc, out, _err = _run(["connect", "slack"])
        self.assertEqual(rc, 1)
        self.assertIn("https://api.slack.com/apps", out)
        self.assertIn("search:read", out)
        # マニフェストは貼り替え先(Create app from manifest)の既定タブに合わせて JSON
        json.loads(slack.SLACK_MANIFEST)
        self.assertIn('"name": "Watari"', out)
        # 実画面の要所（雛形の全選択・置換／インストール／User トークン）が案内に出ている
        self.assertIn("select all", out)
        self.assertIn("Install to Workspace", out)
        self.assertIn("xoxp-", out)


class ConnectorReadSlackTest(_XdgIsolated):
    def setUp(self):
        super().setUp()
        self._saved_http = slack._http
        self._saved_mem = wl.MEM
        self._home = tempfile.TemporaryDirectory(prefix="watari-connread-home-")
        wl.MEM = self._home.name
        connectors.save_auth("slack", "xoxp-secret")

    def tearDown(self):
        slack._http = self._saved_http
        wl.MEM = self._saved_mem
        self._home.cleanup()
        super().tearDown()

    def _match(self, channel_id, ts, channel_name="general", username="example-user", text="hi"):
        return {
            "channel": {"id": channel_id, "name": channel_name},
            "ts": ts, "username": username, "user": "U123", "text": text,
        }

    def test_json_output_is_unified_ascending_and_dedup_across_queries(self):
        captured = {"queries": []}
        # from: クエリと mention クエリで1件重複させる（同じ channel+ts）。
        shared = self._match("C1", "1700000200.000100", text="dup")

        def router(method, url, headers, data):
            self.assertEqual(headers.get("Authorization"), "Bearer xoxp-secret")
            if url == slack.AUTH_TEST_URL:
                return 200, json.dumps(
                    {"ok": True, "user": "example-user", "team": "Example Team", "user_id": "U123"}).encode()
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            query = qs["query"][0]
            captured["queries"].append(query)
            if query.startswith("from:"):
                matches = [self._match("C2", "1700000100.000000", text="from-me"), shared]
            else:
                matches = [shared, self._match("C3", "1700000300.000000", text="mention-me")]
            return 200, json.dumps({"ok": True, "messages": {"matches": matches}}).encode()
        slack._http = _fake_http(router)

        rc, out, err = _run(
            ["connector", "read", "slack", "--since", "2023-11-14T00:00:00.000Z", "--json"])
        self.assertEqual(rc, 0, err)
        rows = json.loads(out)
        self.assertEqual([r["uuid"] for r in rows], [
            "slack:C2:1700000100.000000",
            "slack:C1:1700000200.000100",
            "slack:C3:1700000300.000000",
        ])
        self.assertEqual(set(rows[0].keys()), {"ts", "uuid", "text", "meta"})
        self.assertIn("#general", rows[0]["text"])
        self.assertIn("from-me", rows[0]["text"])
        # 両クエリとも after: に since の日付が付く。
        self.assertTrue(all("after:2023-11-14" in q for q in captured["queries"]))
        self.assertTrue(any(q.startswith("from:<@U123>") for q in captured["queries"]))
        self.assertTrue(any(q.startswith("<@U123>") and not q.startswith("from:")
                             for q in captured["queries"]))

    def test_auth_error_is_nonzero_with_no_partial_output(self):
        slack._http = _fake_http(lambda m, u, h, d: (401, b'{"error":"invalid_auth"}'))
        rc, out, err = _run(["connector", "read", "slack", "--since", "2023-11-14", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("認証に失敗しました", err)
        self.assertIn("watari connect slack", err)  # 再接続コマンドを必ず案内

    def test_search_ok_false_is_nonzero_with_no_partial_output(self):
        def router(method, url, headers, data):
            if url == slack.AUTH_TEST_URL:
                return 200, json.dumps(
                    {"ok": True, "user": "example-user", "team": "Example Team", "user_id": "U123"}).encode()
            return 200, json.dumps({"ok": False, "error": "ratelimited"}).encode()
        slack._http = _fake_http(router)
        rc, out, err = _run(["connector", "read", "slack", "--since", "2023-11-14", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("ratelimited", err)
        self.assertIn("watari connect slack", err)

    def test_bot_token_error_code_is_translated(self):
        """not_allowed_token_type（xoxb を保存してしまった後の読み取り失敗）は英語コードの
        ままにせず、日本語の原因＋貼り直し手順に写像される。"""
        def router(method, url, headers, data):
            if url == slack.AUTH_TEST_URL:
                return 200, json.dumps(
                    {"ok": True, "user": "example-user", "team": "Example Team", "user_id": "U123"}).encode()
            return 200, json.dumps({"ok": False, "error": "not_allowed_token_type"}).encode()
        slack._http = _fake_http(router)
        rc, out, err = _run(["connector", "read", "slack", "--since", "2023-11-14", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("bot 用トークンでは読めません", err)
        self.assertIn("watari connect slack", err)

    def test_missing_scope_error_code_is_translated(self):
        def router(method, url, headers, data):
            if url == slack.AUTH_TEST_URL:
                return 200, json.dumps(
                    {"ok": True, "user": "example-user", "team": "Example Team", "user_id": "U123"}).encode()
            return 200, json.dumps({"ok": False, "error": "missing_scope"}).encode()
        slack._http = _fake_http(router)
        rc, out, err = _run(["connector", "read", "slack", "--since", "2023-11-14", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("search:read", err)
        self.assertIn("watari connect slack", err)

    def test_unconnected_service_is_rejected(self):
        config.save_config(connectors_auth={})  # 未接続に戻す
        rc, out, err = _run(["connector", "read", "slack", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("未接続", err)


class ConnectorWatchCliTest(_XdgIsolated):
    """`watari connector watch slack` で監視チャンネル一覧を設定/表示/解除できる。"""

    def test_set_show_and_clear_watch_channels(self):
        # 設定（# 付き・重複は正規化される）
        rc, out, _ = _run(["connector", "watch", "slack", "#general", "dev-chat", "general"])
        self.assertEqual(rc, 0)
        self.assertIn("#general", out)
        self.assertEqual(config.load_slack_watch_channels(), ["general", "dev-chat"])

        # 表示
        rc, out, _ = _run(["connector", "watch", "slack"])
        self.assertEqual(rc, 0)
        self.assertIn("#general", out)
        self.assertIn("#dev-chat", out)

        # 解除
        rc, out, _ = _run(["connector", "watch", "slack", "--clear"])
        self.assertEqual(rc, 0)
        self.assertEqual(config.load_slack_watch_channels(), [])

        rc, out, _ = _run(["connector", "watch", "slack"])
        self.assertEqual(rc, 0)
        self.assertIn("なし", out)

    def test_watch_rejects_non_slack_service(self):
        rc, out, err = _run(["connector", "watch", "gmail", "general"])
        self.assertEqual(rc, 1)
        self.assertIn("slack", err)


class ConnectorReadSlackWatchTest(_XdgIsolated):
    """監視チャンネル設定時、from:/mention に加えて in:#channel クエリが発行され、
    メンションなしの他人発言（スレッド内の相談など）も拾える。"""

    def setUp(self):
        super().setUp()
        self._saved_http = slack._http
        self._saved_mem = wl.MEM
        self._home = tempfile.TemporaryDirectory(prefix="watari-connwatch-home-")
        wl.MEM = self._home.name
        connectors.save_auth("slack", "xoxp-secret")

    def tearDown(self):
        slack._http = self._saved_http
        wl.MEM = self._saved_mem
        self._home.cleanup()
        super().tearDown()

    def _match(self, channel_id, ts, channel_name="general", username="example-user", text="hi"):
        return {
            "channel": {"id": channel_id, "name": channel_name},
            "ts": ts, "username": username, "user": "U999", "text": text,
        }

    def test_watch_channels_add_channel_queries_and_merge_other_users(self):
        config.save_slack_watch_channels(["#general", "dev-chat"])
        captured = {"queries": []}

        def router(method, url, headers, data):
            if url == slack.AUTH_TEST_URL:
                return 200, json.dumps(
                    {"ok": True, "user": "me", "team": "T", "user_id": "U123"}).encode()
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            query = qs["query"][0]
            captured["queries"].append(query)
            if query.startswith("in:#general"):
                # メンションなしの他人発言（from:/mention クエリでは拾えないもの）
                matches = [self._match("C9", "1700000500.000000",
                                       username="coworker", text="来週の方針どうしよう?")]
            else:
                matches = []
            return 200, json.dumps({"ok": True, "messages": {
                "matches": matches,
                "pagination": {"page": 1, "page_count": 1}}}).encode()
        slack._http = _fake_http(router)

        rc, out, err = _run(
            ["connector", "read", "slack", "--since", "2023-11-14T00:00:00.000Z", "--json"])
        self.assertEqual(rc, 0, err)
        rows = json.loads(out)
        self.assertEqual([r["uuid"] for r in rows], ["slack:C9:1700000500.000000"])
        self.assertIn("coworker", rows[0]["text"])
        self.assertIn("来週の方針どうしよう", rows[0]["text"])
        # from:/mention 2クエリ + 監視2チャンネル = 4クエリ、すべて after: 付き
        self.assertEqual(len(captured["queries"]), 4)
        self.assertTrue(any(q.startswith("in:#general") for q in captured["queries"]))
        self.assertTrue(any(q.startswith("in:#dev-chat") for q in captured["queries"]))
        self.assertTrue(all("after:2023-11-14" in q for q in captured["queries"]))

    def test_no_watch_channels_keeps_two_queries(self):
        captured = {"queries": []}

        def router(method, url, headers, data):
            if url == slack.AUTH_TEST_URL:
                return 200, json.dumps(
                    {"ok": True, "user": "me", "team": "T", "user_id": "U123"}).encode()
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            captured["queries"].append(qs["query"][0])
            return 200, json.dumps({"ok": True, "messages": {"matches": []}}).encode()
        slack._http = _fake_http(router)

        rc, out, err = _run(["connector", "read", "slack", "--json"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(captured["queries"]), 2)

    def test_search_paginates_until_last_page(self):
        config.save_slack_watch_channels(["busy"])
        pages = []

        def router(method, url, headers, data):
            if url == slack.AUTH_TEST_URL:
                return 200, json.dumps(
                    {"ok": True, "user": "me", "team": "T", "user_id": "U123"}).encode()
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            query = qs["query"][0]
            if not query.startswith("in:#busy"):
                return 200, json.dumps({"ok": True, "messages": {"matches": []}}).encode()
            page = int(qs.get("page", ["1"])[0])
            pages.append(page)
            return 200, json.dumps({"ok": True, "messages": {
                "matches": [self._match("CB", f"170000010{page}.000000",
                                        channel_name="busy", text=f"p{page}")],
                "pagination": {"page": page, "page_count": 2}}}).encode()
        slack._http = _fake_http(router)

        rc, out, err = _run(
            ["connector", "read", "slack", "--since", "2023-11-14T00:00:00.000Z", "--json"])
        self.assertEqual(rc, 0, err)
        rows = json.loads(out)
        self.assertEqual(pages, [1, 2])
        self.assertEqual([r["uuid"] for r in rows],
                         ["slack:CB:1700000101.000000", "slack:CB:1700000102.000000"])


# ---------------------------------------------------------------------------
# Chatwork
# ---------------------------------------------------------------------------

class ConnectWizardChatworkTest(_XdgIsolated):
    def setUp(self):
        super().setUp()
        self._saved_http = chatwork._http

    def tearDown(self):
        chatwork._http = self._saved_http
        super().tearDown()

    def _me_ok(self, name="Example User", org="Example Team", token="cw-secret-123"):
        def router(method, url, headers, data):
            self.assertEqual(headers.get("X-ChatWorkToken"), token)
            if url == f"{chatwork.API_BASE}/me":
                return 200, json.dumps({"name": name, "organization_name": org}).encode()
            return 404, b"{}"
        chatwork._http = _fake_http(router)

    def test_success_saves_auth_and_declares_connector(self):
        from watari_cli import prompts
        self._me_ok()
        prompts.text = lambda *a, **k: "cw-secret-123"
        rc, out, err = _run(["connect", "chatwork"])
        self.assertEqual(rc, 0)
        self.assertIn("Example User", out)
        self.assertIn("Example Team", out)
        self.assertNotIn("cw-secret-123", out)  # 認証情報は print しない
        self.assertNotIn("cw-secret-123", err)
        self.assertEqual(connectors.auth_key("chatwork"), "cw-secret-123")
        decl = config.load_connectors()
        self.assertEqual(len(decl), 1)
        self.assertEqual((decl[0]["name"], decl[0]["scope"]), ("chatwork", "cloud"))

    def test_verify_failure_saves_nothing(self):
        from watari_cli import prompts
        prompts.text = lambda *a, **k: "bad-token"
        chatwork._http = _fake_http(lambda m, u, h, d: (401, b'{"errors":["invalid token"]}'))
        rc, out, err = _run(["connect", "chatwork"])
        self.assertEqual(rc, 1)
        self.assertIsNone(connectors.auth_key("chatwork"))
        self.assertEqual(config.load_connectors(), [])
        self.assertNotIn("bad-token", out)
        self.assertNotIn("bad-token", err)

    def test_empty_key_aborts_without_saving(self):
        from watari_cli import prompts
        prompts.text = lambda *a, **k: ""
        rc, _out, err = _run(["connect", "chatwork"])
        self.assertEqual(rc, 1)
        self.assertIsNone(connectors.auth_key("chatwork"))
        self.assertEqual(config.load_connectors(), [])

    def test_guide_gives_token_url_and_menu_path(self):
        """案内は URL を直に示す（画面から辿る道と、管理者による有効化の注意も添える）。"""
        from watari_cli import prompts
        prompts.text = lambda *a, **k: ""  # 空入力で中止させ、案内文だけを見る
        rc, out, _err = _run(["connect", "chatwork"])
        self.assertEqual(rc, 1)
        self.assertIn(
            "https://www.chatwork.com/service/packages/chatwork/subpackages/api/token.php", out)
        self.assertIn("Service integration", out)
        self.assertIn("API Token", out)
        self.assertIn("administrator", out)


class ConnectorReadChatworkTest(_XdgIsolated):
    def setUp(self):
        super().setUp()
        self._saved_http = chatwork._http
        self._saved_mem = wl.MEM
        self._home = tempfile.TemporaryDirectory(prefix="watari-connread-home-")
        wl.MEM = self._home.name
        connectors.save_auth("chatwork", "cw-secret")

    def tearDown(self):
        chatwork._http = self._saved_http
        wl.MEM = self._saved_mem
        self._home.cleanup()
        super().tearDown()

    def _room(self, room_id, last_update_time, name="部屋A"):
        return {"room_id": room_id, "name": name, "last_update_time": last_update_time}

    def _message(self, message_id, send_time, body="hello", account_name="Example User"):
        return {
            "message_id": message_id, "send_time": send_time, "body": body,
            "account": {"account_id": 1, "name": account_name},
        }

    def test_json_output_is_unified_and_ascending(self):
        rooms = [self._room(200, 1700000300, name="Room2"),
                 self._room(100, 1700000100, name="Room1")]  # 応答順はわざと逆
        since_epoch = 1699999000

        def router(method, url, headers, data):
            self.assertEqual(headers.get("X-ChatWorkToken"), "cw-secret")
            if url == f"{chatwork.API_BASE}/rooms":
                return 200, json.dumps(rooms).encode()
            if url == f"{chatwork.API_BASE}/rooms/200/messages?force=1":
                return 200, json.dumps(
                    [self._message(2, 1700000300, body="second")]).encode()
            if url == f"{chatwork.API_BASE}/rooms/100/messages?force=1":
                return 200, json.dumps(
                    [self._message(1, 1700000100, body="first")]).encode()
            return 404, b"{}"
        chatwork._http = _fake_http(router)

        since_iso = chatwork._epoch_to_iso(since_epoch)
        rc, out, err = _run(["connector", "read", "chatwork", "--since", since_iso, "--json"])
        self.assertEqual(rc, 0, err)
        rows = json.loads(out)
        self.assertEqual([r["uuid"] for r in rows], ["chatwork:100:1", "chatwork:200:2"])
        self.assertEqual(set(rows[0].keys()), {"ts", "uuid", "text", "meta"})
        self.assertIn("Room1", rows[0]["text"])
        self.assertIn("Example User", rows[0]["text"])
        self.assertIn("first", rows[0]["text"])

    def test_rooms_not_updated_since_cursor_are_skipped(self):
        rooms = [self._room(1, 1000, name="Old")]

        def router(method, url, headers, data):
            if url == f"{chatwork.API_BASE}/rooms":
                return 200, json.dumps(rooms).encode()
            self.fail(f"部屋メッセージを叩くべきではない: {url}")
        chatwork._http = _fake_http(router)

        since_iso = chatwork._epoch_to_iso(2000)
        rc, out, err = _run(["connector", "read", "chatwork", "--since", since_iso, "--json"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out), [])

    def test_auth_error_is_nonzero_with_no_partial_output(self):
        chatwork._http = _fake_http(lambda m, u, h, d: (401, b'{"errors":["invalid token"]}'))
        rc, out, err = _run(["connector", "read", "chatwork", "--since", "2023-11-14", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("認証に失敗しました", err)
        self.assertIn("watari connect chatwork", err)

    def test_unconnected_service_is_rejected(self):
        config.save_config(connectors_auth={})  # 未接続に戻す
        rc, out, err = _run(["connector", "read", "chatwork", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("未接続", err)


if __name__ == "__main__":
    unittest.main()
