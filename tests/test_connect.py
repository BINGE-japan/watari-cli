"""組み込みコネクタ（`watari connect` / `watari connector read`）の契約テスト。

第一弾サービス = linear。実 API は叩かず HTTP をモックしてオフライン検証する
（cloud.py/test_cloud.py と同じやり方: linear._http を差し替える）。固めること:
- `watari connect linear`：案内 → 貼り付け → 疎通確認(viewer) → config 保存 → connector 宣言。
  失敗時（空入力・認証エラー）は何も保存しない。API キーは stdout/stderr に一切出さない。
- `watari connect`（引数なし）：選択メニューから同じ経路に入る。
- `watari connect slack` 等の未対応サービス：「未対応」を返すだけで何も保存しない。
- `watari connector read linear`：統一形式 {ts,uuid,text,meta} をカーソル(--since 省略時は
  host record のカーソル)以降・updatedAt 昇順で返す。認証エラー/未接続は非ゼロ終了・出力なし。
- `watari connector list`：組み込み/カスタムを区別して表示。

注: connectors_auth・connectors 宣言は config.json（XDG_CONFIG_HOME 配下）に載るためテストは
それを隔離する。host カーソルは WATARI_HOME 側（wl.MEM）にあるが、wl.MEM は import 時に一度だけ
env から解決されるモジュール定数なので、--home 経由では反映されない（test_connectors.py と同じ
理由）。読み取りテストは wl.MEM を直接差し替える。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.parse

from watari_cli import config, connectors, github, host, linear, notion
from watari_cli.cli import _build_parser
from watari_cli.engine import watari_lib as wl


def _run(argv):
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


class ConnectWizardTest(_XdgIsolated):
    def setUp(self):
        super().setUp()
        self._saved_http = linear._http

    def tearDown(self):
        linear._http = self._saved_http
        super().tearDown()

    def _viewer_ok(self, name="Binge", secret="sekret-key-123"):
        def router(method, url, headers, data):
            payload = json.loads(data)
            self.assertEqual(headers.get("Authorization"), secret)  # 生キーをそのまま送る
            if "viewer" in payload["query"]:
                return 200, json.dumps(
                    {"data": {"viewer": {"name": name, "email": "b@example.com"}}}).encode()
            return 404, b"{}"
        linear._http = _fake_http(router)

    def test_success_saves_auth_and_declares_connector(self):
        from watari_cli import prompts
        self._viewer_ok()
        prompts.text = lambda *a, **k: "sekret-key-123"
        rc, out, err = _run(["connect", "linear"])
        self.assertEqual(rc, 0)
        self.assertIn("Binge", out)
        self.assertNotIn("sekret-key-123", out)  # 認証情報は print しない
        self.assertNotIn("sekret-key-123", err)
        self.assertEqual(connectors.auth_key("linear"), "sekret-key-123")
        decl = config.load_connectors()
        self.assertEqual(len(decl), 1)
        self.assertEqual((decl[0]["name"], decl[0]["scope"]), ("linear", "cloud"))

    def test_verify_failure_saves_nothing(self):
        from watari_cli import prompts
        prompts.text = lambda *a, **k: "bad-key"
        linear._http = _fake_http(lambda m, u, h, d: (401, b'{"error":"unauthorized"}'))
        rc, out, err = _run(["connect", "linear"])
        self.assertEqual(rc, 1)
        self.assertIsNone(connectors.auth_key("linear"))
        self.assertEqual(config.load_connectors(), [])
        self.assertNotIn("bad-key", out)
        self.assertNotIn("bad-key", err)

    def test_empty_key_aborts_without_saving(self):
        from watari_cli import prompts
        prompts.text = lambda *a, **k: ""
        rc, _out, err = _run(["connect", "linear"])
        self.assertEqual(rc, 1)
        self.assertIsNone(connectors.auth_key("linear"))
        self.assertEqual(config.load_connectors(), [])

    def test_planned_service_reports_unimplemented_and_saves_nothing(self):
        # slack は実装済みになったため、未対応プレースホルダの例は gmail に差し替える
        # （gmail/calendar は本タスクのスコープ外で未対応のまま）。
        rc, out, _err = _run(["connect", "gmail"])
        self.assertEqual(rc, 0)
        self.assertIn("未対応", out)
        self.assertIn("対応予定", out)
        self.assertEqual(config.load_connectors(), [])

    def test_unknown_service_is_an_error(self):
        rc, _out, err = _run(["connect", "not-a-real-service"])
        self.assertEqual(rc, 2)
        self.assertIn("不明", err)

    def test_menu_dispatches_selected_service(self):
        from watari_cli import prompts
        self._viewer_ok(name="Binge", secret="key123")
        prompts.select = lambda *a, **k: "linear"
        prompts.text = lambda *a, **k: "key123"
        rc, out, _err = _run(["connect"])
        self.assertEqual(rc, 0)
        self.assertEqual(connectors.auth_key("linear"), "key123")


class ConnectorReadLinearTest(_XdgIsolated):
    def setUp(self):
        super().setUp()
        self._saved_http = linear._http
        self._saved_mem = wl.MEM
        self._home = tempfile.TemporaryDirectory(prefix="watari-connread-home-")
        wl.MEM = self._home.name
        connectors.save_auth("linear", "sekret")

    def tearDown(self):
        linear._http = self._saved_http
        wl.MEM = self._saved_mem
        self._home.cleanup()
        super().tearDown()

    def _issue(self, identifier, updated, title="t", state="Todo"):
        return {
            "identifier": identifier, "title": title, "url": f"https://linear.app/x/{identifier}",
            "updatedAt": updated, "dueDate": None, "state": {"name": state},
            "comments": {"nodes": []},
        }

    def test_json_output_is_unified_and_ascending(self):
        nodes = [self._issue("ABC-2", "2026-07-15T00:00:00.000Z"),
                 self._issue("ABC-1", "2026-07-10T00:00:00.000Z")]  # 応答順はわざと逆
        captured = {}

        def router(method, url, headers, data):
            payload = json.loads(data)
            captured["variables"] = payload["variables"]
            return 200, json.dumps({"data": {"issues": {"nodes": nodes}}}).encode()
        linear._http = _fake_http(router)

        rc, out, err = _run(
            ["connector", "read", "linear", "--since", "2026-07-01T00:00:00.000Z", "--json"])
        self.assertEqual(rc, 0, err)
        rows = json.loads(out)
        self.assertEqual([r["uuid"] for r in rows],
                         ["linear:ABC-1@2026-07-10", "linear:ABC-2@2026-07-15"])
        self.assertEqual(set(rows[0].keys()), {"ts", "uuid", "text", "meta"})
        self.assertIn("ABC-1", rows[0]["text"])
        self.assertEqual(captured["variables"]["since"], "2026-07-01T00:00:00.000Z")

    def test_auth_error_is_nonzero_with_no_partial_output(self):
        linear._http = _fake_http(lambda m, u, h, d: (401, b'{"error":"unauthorized"}'))
        rc, out, err = _run(["connector", "read", "linear", "--since", "2026-07-01", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("認証エラー", err)

    def test_since_defaults_to_host_cursor_when_omitted(self):
        host.save_cursors(self._home.name, {"linear": "2026-07-01T00:00:00.000Z"})
        captured = {}

        def router(method, url, headers, data):
            captured["variables"] = json.loads(data)["variables"]
            return 200, json.dumps({"data": {"issues": {"nodes": []}}}).encode()
        linear._http = _fake_http(router)

        rc, _out, err = _run(["connector", "read", "linear", "--json"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(captured["variables"]["since"], "2026-07-01T00:00:00.000Z")

    def test_unconnected_service_is_rejected(self):
        config.save_config(connectors_auth={})  # 未接続に戻す
        rc, out, err = _run(["connector", "read", "linear", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("未接続", err)

    def test_unknown_connector_name_is_rejected(self):
        rc, out, err = _run(["connector", "read", "ghost", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("組み込みコネクタではありません", err)


class ConnectWizardGithubTest(_XdgIsolated):
    def setUp(self):
        super().setUp()
        self._saved_http = github._http

    def tearDown(self):
        github._http = self._saved_http
        super().tearDown()

    def _user_ok(self, login="bingedev", token="ghp-secret-123"):
        def router(method, url, headers, data):
            self.assertEqual(headers.get("Authorization"), f"Bearer {token}")
            if url == "https://api.github.com/user":
                return 200, json.dumps({"login": login}).encode()
            return 404, b"{}"
        github._http = _fake_http(router)

    def test_success_saves_auth_and_declares_connector(self):
        from watari_cli import prompts
        self._user_ok()
        prompts.text = lambda *a, **k: "ghp-secret-123"
        rc, out, err = _run(["connect", "github"])
        self.assertEqual(rc, 0)
        self.assertIn("bingedev", out)
        self.assertNotIn("ghp-secret-123", out)  # 認証情報は print しない
        self.assertNotIn("ghp-secret-123", err)
        self.assertEqual(connectors.auth_key("github"), "ghp-secret-123")
        decl = config.load_connectors()
        self.assertEqual(len(decl), 1)
        self.assertEqual((decl[0]["name"], decl[0]["scope"]), ("github", "cloud"))

    def test_verify_failure_saves_nothing(self):
        from watari_cli import prompts
        prompts.text = lambda *a, **k: "bad-token"
        github._http = _fake_http(lambda m, u, h, d: (401, b'{"message":"Bad credentials"}'))
        rc, out, err = _run(["connect", "github"])
        self.assertEqual(rc, 1)
        self.assertIsNone(connectors.auth_key("github"))
        self.assertEqual(config.load_connectors(), [])
        self.assertNotIn("bad-token", out)
        self.assertNotIn("bad-token", err)

    def test_empty_key_aborts_without_saving(self):
        from watari_cli import prompts
        prompts.text = lambda *a, **k: ""
        rc, _out, err = _run(["connect", "github"])
        self.assertEqual(rc, 1)
        self.assertIsNone(connectors.auth_key("github"))
        self.assertEqual(config.load_connectors(), [])

    def test_guide_mentions_token_creation_url(self):
        from watari_cli import prompts
        prompts.text = lambda *a, **k: ""  # 空入力で中止させ、案内文だけを見る
        rc, out, _err = _run(["connect", "github"])
        self.assertEqual(rc, 1)
        self.assertIn("https://github.com/settings/tokens", out)


class ConnectorReadGithubTest(_XdgIsolated):
    def setUp(self):
        super().setUp()
        self._saved_http = github._http
        self._saved_mem = wl.MEM
        self._home = tempfile.TemporaryDirectory(prefix="watari-connread-home-")
        wl.MEM = self._home.name
        connectors.save_auth("github", "ghp-secret")

    def tearDown(self):
        github._http = self._saved_http
        wl.MEM = self._saved_mem
        self._home.cleanup()
        super().tearDown()

    def _item(self, number, updated, repo="binge/watari-cli", title="t", state="open"):
        return {
            "number": number, "title": title, "state": state, "updated_at": updated,
            "html_url": f"https://github.com/{repo}/issues/{number}",
            "repository_url": f"https://api.github.com/repos/{repo}",
            "comments": 2,
        }

    def test_json_output_is_unified_and_ascending(self):
        items = [self._item(20, "2026-07-15T00:00:00Z"),
                 self._item(10, "2026-07-10T00:00:00Z")]  # 応答順はわざと逆
        captured = {}

        def router(method, url, headers, data):
            self.assertEqual(headers.get("Authorization"), "Bearer ghp-secret")
            if url == "https://api.github.com/user":
                return 200, json.dumps({"login": "bingedev"}).encode()
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            captured["q"] = qs["q"][0]
            captured["order"] = qs["order"][0]
            return 200, json.dumps({"items": items}).encode()
        github._http = _fake_http(router)

        rc, out, err = _run(
            ["connector", "read", "github", "--since", "2026-07-01T00:00:00Z", "--json"])
        self.assertEqual(rc, 0, err)
        rows = json.loads(out)
        self.assertEqual([r["uuid"] for r in rows],
                         ["github:binge/watari-cli#10@2026-07-10",
                          "github:binge/watari-cli#20@2026-07-15"])
        self.assertEqual(set(rows[0].keys()), {"ts", "uuid", "text", "meta"})
        self.assertIn("binge/watari-cli#10", rows[0]["text"])
        self.assertEqual(captured["q"], "involves:bingedev updated:>2026-07-01T00:00:00Z")
        self.assertEqual(captured["order"], "asc")

    def test_auth_error_is_nonzero_with_no_partial_output(self):
        github._http = _fake_http(lambda m, u, h, d: (401, b'{"message":"Bad credentials"}'))
        rc, out, err = _run(["connector", "read", "github", "--since", "2026-07-01", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("認証エラー", err)

    def test_unconnected_service_is_rejected(self):
        config.save_config(connectors_auth={})  # 未接続に戻す
        rc, out, err = _run(["connector", "read", "github", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("未接続", err)


class ConnectWizardNotionTest(_XdgIsolated):
    def setUp(self):
        super().setUp()
        self._saved_http = notion._http

    def tearDown(self):
        notion._http = self._saved_http
        super().tearDown()

    def _me_ok(self, name="Watari Bot", workspace="Binge Workspace", token="ntn-secret-123"):
        def router(method, url, headers, data):
            self.assertEqual(headers.get("Authorization"), f"Bearer {token}")
            self.assertEqual(headers.get("Notion-Version"), "2022-06-28")
            if url == "https://api.notion.com/v1/users/me":
                return 200, json.dumps(
                    {"name": name, "bot": {"workspace_name": workspace}}).encode()
            return 404, b"{}"
        notion._http = _fake_http(router)

    def test_success_saves_auth_and_declares_connector(self):
        from watari_cli import prompts
        self._me_ok()
        prompts.text = lambda *a, **k: "ntn-secret-123"
        rc, out, err = _run(["connect", "notion"])
        self.assertEqual(rc, 0)
        self.assertIn("Watari Bot", out)
        self.assertNotIn("ntn-secret-123", out)  # 認証情報は print しない
        self.assertNotIn("ntn-secret-123", err)
        self.assertEqual(connectors.auth_key("notion"), "ntn-secret-123")
        decl = config.load_connectors()
        self.assertEqual(len(decl), 1)
        self.assertEqual((decl[0]["name"], decl[0]["scope"]), ("notion", "cloud"))

    def test_verify_failure_saves_nothing(self):
        from watari_cli import prompts
        prompts.text = lambda *a, **k: "bad-token"
        notion._http = _fake_http(lambda m, u, h, d: (401, b'{"message":"unauthorized"}'))
        rc, out, err = _run(["connect", "notion"])
        self.assertEqual(rc, 1)
        self.assertIsNone(connectors.auth_key("notion"))
        self.assertEqual(config.load_connectors(), [])
        self.assertNotIn("bad-token", out)
        self.assertNotIn("bad-token", err)

    def test_empty_key_aborts_without_saving(self):
        from watari_cli import prompts
        prompts.text = lambda *a, **k: ""
        rc, _out, err = _run(["connect", "notion"])
        self.assertEqual(rc, 1)
        self.assertIsNone(connectors.auth_key("notion"))
        self.assertEqual(config.load_connectors(), [])

    def test_guide_mentions_integration_setup_url_and_connection_step(self):
        from watari_cli import prompts
        prompts.text = lambda *a, **k: ""  # 空入力で中止させ、案内文だけを見る
        rc, out, _err = _run(["connect", "notion"])
        self.assertEqual(rc, 1)
        self.assertIn("https://www.notion.so/my-integrations", out)
        self.assertIn("Connections", out)  # 2段目（ページ/DB への接続）の案内が含まれる


class ConnectorReadNotionTest(_XdgIsolated):
    def setUp(self):
        super().setUp()
        self._saved_http = notion._http
        self._saved_mem = wl.MEM
        self._home = tempfile.TemporaryDirectory(prefix="watari-connread-home-")
        wl.MEM = self._home.name
        connectors.save_auth("notion", "ntn-secret")

    def tearDown(self):
        notion._http = self._saved_http
        wl.MEM = self._saved_mem
        self._home.cleanup()
        super().tearDown()

    def _page(self, page_id, updated, title="Title"):
        return {
            "id": page_id, "url": f"https://notion.so/{page_id}",
            "last_edited_time": updated,
            "properties": {"Name": {"type": "title", "title": [{"plain_text": title}]}},
        }

    def test_json_output_is_unified_and_ascending(self):
        pages = [self._page("page-2", "2026-07-15T00:00:00.000Z", "B"),
                 self._page("page-1", "2026-07-10T00:00:00.000Z", "A")]  # 応答順はわざと逆
        captured = {}

        def router(method, url, headers, data):
            if url == "https://api.notion.com/v1/search":
                captured["payload"] = json.loads(data)
                return 200, json.dumps({"results": pages}).encode()
            return 404, b"{}"
        notion._http = _fake_http(router)

        rc, out, err = _run(
            ["connector", "read", "notion", "--since", "2026-07-01T00:00:00.000Z", "--json"])
        self.assertEqual(rc, 0, err)
        rows = json.loads(out)
        self.assertEqual([r["uuid"] for r in rows],
                         ["notion:page-1@2026-07-10", "notion:page-2@2026-07-15"])
        self.assertEqual(set(rows[0].keys()), {"ts", "uuid", "text", "meta"})
        self.assertIn("A", rows[0]["text"])
        self.assertEqual(captured["payload"]["sort"],
                         {"direction": "descending", "timestamp": "last_edited_time"})
        self.assertEqual(captured["payload"]["filter"], {"value": "page", "property": "object"})

    def test_since_filters_out_older_pages_client_side(self):
        # 実 API は降順（新しい順）で返す——古いページに到達した時点で打ち切られることも同時に検証
        pages = [self._page("page-new", "2026-07-15T00:00:00.000Z", "New"),
                 self._page("page-old", "2026-06-01T00:00:00.000Z", "Old")]
        notion._http = _fake_http(
            lambda m, u, h, d: (200, json.dumps({"results": pages}).encode()))
        rc, out, err = _run(
            ["connector", "read", "notion", "--since", "2026-07-01T00:00:00.000Z", "--json"])
        self.assertEqual(rc, 0, err)
        rows = json.loads(out)
        self.assertEqual([r["uuid"] for r in rows], ["notion:page-new@2026-07-15"])

    def test_auth_error_is_nonzero_with_no_partial_output(self):
        notion._http = _fake_http(lambda m, u, h, d: (401, b'{"message":"unauthorized"}'))
        rc, out, err = _run(["connector", "read", "notion", "--since", "2026-07-01", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("認証エラー", err)

    def test_unconnected_service_is_rejected(self):
        config.save_config(connectors_auth={})  # 未接続に戻す
        rc, out, err = _run(["connector", "read", "notion", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("未接続", err)


class RegistryExtensibilityTest(_XdgIsolated):
    """新サービスは connectors.REGISTRY に1件足すだけで、connect メニューと connector read の
    両方に現れることを固める（cli/__init__.py・connectors.py にサービス名を書き足さなくてよい）。"""

    def setUp(self):
        super().setUp()
        self._saved_registry = dict(connectors.REGISTRY)

    def tearDown(self):
        connectors.REGISTRY.clear()
        connectors.REGISTRY.update(self._saved_registry)
        super().tearDown()

    def test_new_registry_entry_appears_in_menu_and_is_readable(self):
        from watari_cli import prompts

        def fake_verify(api_key):
            return True, "Fake Viewer"

        def fake_read(api_key, since):
            return [{"ts": "2026-07-01T00:00:00.000Z", "uuid": "fakesvc:1@2026-07-01",
                     "text": f"hello via {api_key}", "meta": {}}]

        connectors.REGISTRY["fakesvc"] = lambda: connectors.ServiceAdapter(
            label="FakeService", implemented=True,
            guide=["どこかで発行したキーを貼り付けてください"], verify=fake_verify, read=fake_read)

        captured = {}

        def fake_select(message, options, default=0):
            captured["options"] = options
            return "fakesvc"
        prompts.select = fake_select
        prompts.text = lambda *a, **k: "fake-api-key"

        # メニューに現れる（cli 側はレジストリを列挙しただけ・"fakesvc" を知らない）
        rc, out, _err = _run(["connect"])
        self.assertEqual(rc, 0)
        self.assertIn(("FakeService", "fakesvc"), captured["options"])
        self.assertIn("Fake Viewer", out)
        self.assertEqual(connectors.auth_key("fakesvc"), "fake-api-key")
        self.assertEqual(config.load_connectors()[0]["name"], "fakesvc")

        # connector read にも現れる（read の実装はレジストリのアダプタがそのまま提供）
        rc, out, err = _run(["connector", "read", "fakesvc", "--json"])
        self.assertEqual(rc, 0, err)
        rows = json.loads(out)
        self.assertEqual(rows, [{"ts": "2026-07-01T00:00:00.000Z",
                                 "uuid": "fakesvc:1@2026-07-01",
                                 "text": "hello via fake-api-key", "meta": {}}])

        # connector list も組み込みとして表示する
        rc, out, _err = _run(["connector", "list"])
        self.assertIn("fakesvc", out)
        self.assertIn("組み込み", out)


class ConnectorListDistinguishesKindTest(_XdgIsolated):
    def test_list_shows_builtin_vs_custom(self):
        config.save_connector({"name": "linear", "scope": "cloud", "read": "組み込み"})
        config.save_connector({"name": "tasks", "scope": "local", "read": "自由指示"})
        rc, out, _err = _run(["connector", "list"])
        self.assertEqual(rc, 0)
        self.assertIn("linear", out)
        self.assertIn("組み込み", out)
        self.assertIn("tasks", out)
        self.assertIn("カスタム", out)


if __name__ == "__main__":
    unittest.main()
