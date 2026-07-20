"""freee（クラウド会計）connector の契約テスト。

linear/slack/chatwork と違い、freee は貼り付けるのが「トークン1個」ではなく Client ID/Secret で、
そのあとブラウザ認可（loopback/oob）→トークン交換→事業所選択まで `freee.verify()` の中で完結する
（auth_kind="oauth" の「貼り付けプロンプトなし」経路に freee 独自のロジックを乗せている）。
実ソケット/実ブラウザは通さない——`freee._run_authorization` を丸ごと差し替えて (code,
redirect_uri) を返すだけにする（test_connect_google.py が cloud.authorize を丸ごと差し替えるのと
同じやり方）。HTTP は `freee._http` を差し替えてオフライン検証する。固めること:
- 認可コード交換で access_token/refresh_token が connectors_auth.freee に保存されること。
- **リフレッシュのたびに新しい refresh_token へ差し替わること**（freee のリフレッシュトークンは
  使い捨て＝ローテーションするため、取りこぼすと次回から認証不能になる回帰テスト）。
- invalid_grant のとき「再接続が必要です」と明示するエラーになること。
- 事業所が複数あるとき prompts.select で選ばせ、company_id が保存されること。
- read が統一形式 {ts,uuid,text,meta} を発生日昇順で返すこと。
- guide に登録URL（https://app.secure.freee.co.jp/developers/applications）とコールバックURLの
  既定値（http://127.0.0.1:8787）が含まれること。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest

from watari_cli import config, connectors, freee, host
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
    """XDG_CONFIG_HOME を隔離し、freee._http / _run_authorization / prompts を差し替える。"""

    def setUp(self):
        self._cfg = tempfile.TemporaryDirectory(prefix="watari-connect-freee-cfg-")
        self._saved_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._cfg.name

        self._saved_http = freee._http
        self._saved_run_auth = freee._run_authorization
        from watari_cli import prompts
        self._saved_prompts = {"text": prompts.text, "select": prompts.select}

        # 実ソケット/実ブラウザは通さない：常に固定の (code, redirect_uri) を返す。
        freee._run_authorization = lambda client_id: ("AUTHCODE", "http://127.0.0.1:8787")

    def tearDown(self):
        freee._http = self._saved_http
        freee._run_authorization = self._saved_run_auth
        from watari_cli import prompts
        prompts.text = self._saved_prompts["text"]
        prompts.select = self._saved_prompts["select"]
        if self._saved_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._saved_xdg
        self._cfg.cleanup()

    @staticmethod
    def _queued_text(values):
        """prompts.text の差し替え用：呼ばれるたびに順番に values を返す。"""
        it = iter(values)

        def fn(*a, **k):
            return next(it)
        return fn


def _token_response(access="AT1", refresh="RT1", **extra):
    body = {"access_token": access, "token_type": "bearer", "expires_in": 21600,
            "refresh_token": refresh, "scope": "read write"}
    body.update(extra)
    return 200, json.dumps(body).encode()


def _companies_response(companies):
    return 200, json.dumps({"companies": companies}).encode()


class ConnectWizardFreeeTest(_XdgIsolated):
    def _router_single_company(self, refresh="RT1"):
        def router(method, url, headers=None, data=None):
            if url == freee.TOKEN_URL:
                return _token_response(refresh=refresh)
            if url.startswith(freee.COMPANIES_URL):
                self.assertEqual(headers.get("Authorization"), "Bearer AT1")
                return _companies_response(
                    [{"id": 1, "display_name": "株式会社テスト"}])
            return 404, b"{}"
        freee._http = _fake_http(router)

    def test_success_exchanges_code_and_saves_access_and_refresh(self):
        from watari_cli import prompts
        prompts.text = self._queued_text(["cid-123", "csecret-456"])
        self._router_single_company()

        rc, out, err = _run(["connect", "freee"])
        self.assertEqual(rc, 0, err)
        self.assertIn("株式会社テスト", out)
        self.assertNotIn("csecret-456", out)  # 認証情報は print しない
        self.assertNotIn("csecret-456", err)

        saved = config.load_config()["connectors_auth"]["freee"]
        self.assertEqual(saved["client_id"], "cid-123")
        self.assertEqual(saved["client_secret"], "csecret-456")
        self.assertEqual(saved["refresh_token"], "RT1")
        self.assertEqual(saved["company_id"], 1)

        decl = config.load_connectors()
        self.assertEqual(len(decl), 1)
        self.assertEqual((decl[0]["name"], decl[0]["scope"]), ("freee", "cloud"))

    def test_token_exchange_failure_saves_nothing(self):
        from watari_cli import prompts
        prompts.text = self._queued_text(["cid-123", "csecret-456"])
        freee._http = _fake_http(lambda m, u, h, d: (
            400, json.dumps({"error": "invalid_request"}).encode()))

        rc, out, err = _run(["connect", "freee"])
        self.assertEqual(rc, 1)
        self.assertEqual(config.load_config().get("connectors_auth", {}).get("freee"), None)
        self.assertEqual(config.load_connectors(), [])

    def test_empty_client_id_aborts_without_saving(self):
        from watari_cli import prompts
        prompts.text = self._queued_text(["", "csecret-456"])
        rc, _out, err = _run(["connect", "freee"])
        self.assertEqual(rc, 1)
        self.assertEqual(config.load_config().get("connectors_auth", {}).get("freee"), None)
        self.assertEqual(config.load_connectors(), [])

    def test_multiple_companies_prompts_select_and_saves_chosen_id(self):
        from watari_cli import prompts
        prompts.text = self._queued_text(["cid-123", "csecret-456"])
        captured = {}

        def fake_select(message, options, default=0):
            captured["options"] = options
            return options[1][1]  # 2番目の事業所を選ぶ
        prompts.select = fake_select

        def router(method, url, headers=None, data=None):
            if url == freee.TOKEN_URL:
                return _token_response()
            if url.startswith(freee.COMPANIES_URL):
                return _companies_response([
                    {"id": 1, "display_name": "会社A"},
                    {"id": 2, "display_name": "会社B"},
                ])
            return 404, b"{}"
        freee._http = _fake_http(router)

        rc, out, err = _run(["connect", "freee"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(captured["options"]), 2)
        saved = config.load_config()["connectors_auth"]["freee"]
        self.assertEqual(saved["company_id"], 2)
        self.assertIn("会社B", out)

    def test_guide_mentions_registration_url_and_default_callback(self):
        service = connectors.get_service("freee")
        guide_text = "\n".join(service.guide)
        self.assertIn("https://app.secure.freee.co.jp/developers/applications", guide_text)
        self.assertIn("http://127.0.0.1:8787", guide_text)

    def test_menu_includes_freee(self):
        from watari_cli import prompts

        def fake_select(message, options, default=0):
            raise prompts.Cancelled
        prompts.select = fake_select
        rc, _out, _err = _run(["connect"])
        self.assertEqual(rc, 130)


class TokenRotationTest(_XdgIsolated):
    """更新のたびに refresh_token が新しい値へ差し替わることの回帰テスト（最重要）。"""

    def setUp(self):
        super().setUp()
        config.save_config(connectors_auth={"freee": {
            "client_id": "cid-123", "client_secret": "csecret-456",
            "refresh_token": "RT-old", "company_id": 1,
        }})

    def test_refresh_replaces_stored_refresh_token(self):
        captured = {}

        def router(method, url, headers=None, data=None):
            self.assertEqual(url, freee.TOKEN_URL)
            captured["body"] = data
            return _token_response(access="AT-new", refresh="RT-new")
        freee._http = _fake_http(router)

        token = freee.access_token()
        self.assertEqual(token, "AT-new")

        saved = config.load_config()["connectors_auth"]["freee"]
        self.assertEqual(saved["refresh_token"], "RT-new")
        self.assertNotEqual(saved["refresh_token"], "RT-old")
        # 他のフィールドは保持される。
        self.assertEqual(saved["client_id"], "cid-123")
        self.assertEqual(saved["company_id"], 1)
        self.assertIn(b"grant_type=refresh_token", captured["body"])
        self.assertIn(b"refresh_token=RT-old", captured["body"])

    def test_second_refresh_uses_rotated_token_not_the_original(self):
        calls = []

        def router(method, url, headers=None, data=None):
            calls.append(data)
            if b"refresh_token=RT-old" in data:
                return _token_response(access="AT-1", refresh="RT-1")
            if b"refresh_token=RT-1" in data:
                return _token_response(access="AT-2", refresh="RT-2")
            return 400, json.dumps({"error": "invalid_grant"}).encode()
        freee._http = _fake_http(router)

        self.assertEqual(freee.access_token(), "AT-1")
        self.assertEqual(freee.access_token(), "AT-2")
        saved = config.load_config()["connectors_auth"]["freee"]
        self.assertEqual(saved["refresh_token"], "RT-2")

    def test_invalid_grant_raises_clear_reconnect_error(self):
        freee._http = _fake_http(lambda m, u, h, d: (
            400, json.dumps({"error": "invalid_grant",
                             "error_description": "expired"}).encode()))
        with self.assertRaises(connectors.ConnectorError) as ctx:
            freee.access_token()
        self.assertIn("再接続", str(ctx.exception))
        self.assertIn("watari connect freee", str(ctx.exception))
        # 失敗時は既存の refresh_token を書き換えない。
        saved = config.load_config()["connectors_auth"]["freee"]
        self.assertEqual(saved["refresh_token"], "RT-old")

    def test_missing_refresh_token_in_response_is_a_clear_error(self):
        freee._http = _fake_http(lambda m, u, h, d: (
            200, json.dumps({"access_token": "AT-new"}).encode()))
        with self.assertRaises(connectors.ConnectorError) as ctx:
            freee.access_token()
        self.assertIn("再接続", str(ctx.exception))


class ConnectorReadFreeeTest(_XdgIsolated):
    def setUp(self):
        super().setUp()
        self._saved_mem = wl.MEM
        self._home = tempfile.TemporaryDirectory(prefix="watari-connread-freee-home-")
        wl.MEM = self._home.name
        config.save_config(connectors_auth={"freee": {
            "client_id": "cid-123", "client_secret": "csecret-456",
            "refresh_token": "RT-old", "company_id": 42,
        }})

    def tearDown(self):
        wl.MEM = self._saved_mem
        self._home.cleanup()
        super().tearDown()

    def _deal(self, deal_id, issue_date, amount=1000, partner_id=9,
             account_item_id=100, description="打ち合わせ"):
        return {
            "id": deal_id, "company_id": 42, "issue_date": issue_date, "amount": amount,
            "type": "expense", "partner_id": partner_id,
            "details": [{"account_item_id": account_item_id, "description": description}],
        }

    def test_json_output_is_unified_and_ascending(self):
        deals = [self._deal(2, "2026-07-15", amount=5000),
                self._deal(1, "2026-07-01", amount=3000)]  # 応答順はわざと逆

        def router(method, url, headers=None, data=None):
            if url == freee.TOKEN_URL:
                return _token_response(access="AT-x", refresh="RT-x")
            if url.startswith(freee.DEALS_URL):
                self.assertEqual(headers.get("Authorization"), "Bearer AT-x")
                self.assertIn("company_id=42", url)
                self.assertIn("start_issue_date=2026-07-01", url)
                return 200, json.dumps({"deals": deals}).encode()
            return 404, b"{}"
        freee._http = _fake_http(router)

        rc, out, err = _run(["connector", "read", "freee", "--since",
                             "2026-07-01T00:00:00.000Z", "--json"])
        self.assertEqual(rc, 0, err)
        rows = json.loads(out)
        self.assertEqual([r["uuid"] for r in rows],
                         ["freee:deal:1@2026-07-01", "freee:deal:2@2026-07-15"])
        self.assertEqual(set(rows[0].keys()), {"ts", "uuid", "text", "meta"})
        self.assertIn("[取引]", rows[0]["text"])
        self.assertIn("3,000円", rows[0]["text"])
        self.assertIn("5,000円", rows[1]["text"])

    def test_unconnected_without_company_id_is_rejected(self):
        config.save_config(connectors_auth={"freee": {
            "client_id": "cid-123", "client_secret": "csecret-456", "refresh_token": "RT-old"}})
        rc, out, err = _run(["connector", "read", "freee", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("未接続", err)

    def test_invalid_grant_is_nonzero_with_reconnect_message(self):
        freee._http = _fake_http(lambda m, u, h, d: (
            400, json.dumps({"error": "invalid_grant"}).encode()))
        rc, out, err = _run(["connector", "read", "freee", "--since", "2026-07-01", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("再接続", err)

    def test_since_defaults_to_host_cursor_when_omitted(self):
        host.save_cursors(self._home.name, {"freee": "2026-07-10T00:00:00.000Z"})
        captured = {}

        def router(method, url, headers=None, data=None):
            if url == freee.TOKEN_URL:
                return _token_response(access="AT-x", refresh="RT-x")
            captured["url"] = url
            return 200, json.dumps({"deals": []}).encode()
        freee._http = _fake_http(router)
        rc, _out, err = _run(["connector", "read", "freee", "--json"])
        self.assertEqual(rc, 0, err)
        self.assertIn("start_issue_date=2026-07-10", captured["url"])


class RegistryFreeeExtensionTest(_XdgIsolated):
    def test_freee_is_implemented_oauth_with_custom_connected_hook(self):
        service = connectors.get_service("freee")
        self.assertIsNotNone(service)
        self.assertTrue(service.implemented)
        self.assertEqual(service.auth_kind, "oauth")
        self.assertIsNotNone(service.connected)

    def test_is_connected_false_when_nothing_saved(self):
        self.assertFalse(connectors.is_connected("freee"))

    def test_is_connected_true_once_fully_saved(self):
        config.save_config(connectors_auth={"freee": {
            "client_id": "cid", "client_secret": "csec",
            "refresh_token": "rt", "company_id": 1}})
        self.assertTrue(connectors.is_connected("freee"))


if __name__ == "__main__":
    unittest.main()
