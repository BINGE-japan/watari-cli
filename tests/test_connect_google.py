"""gmail / calendar / gdrive（Google 系組み込みコネクタ）の契約テスト。

linear/github/notion と違い認証がトークン貼り付けではなく cloud.py の共有 Google OAuth
（incremental scope）なので、tests/test_connect.py には追記せずこのファイルに独立させる（並行して
slack/chatwork の作業が進行中で、そちらのファイル群には一切触れない）。実 Google エンドポイントは
叩かず、cloud.authorize と HTTP をモックしてオフライン検証する。固めること:
- `watari connect gmail|calendar|gdrive`：必要スコープが未付与なら cloud.authorize が
  ちょうどそのスコープで呼ばれ、承認成功後に connector 宣言まで進む。paste 系と違い
  「貼り付けてください」プロンプトは一切出ない。
- 既に必要スコープが付与済みなら authorize を呼ばずに疎通確認だけで完了する。
- `watari connector read <name>`：統一形式 {ts,uuid,text,meta} を ts 昇順で返す。
- 401/403 は明確な非ゼロ終了（403 はスコープ不足の可能性を案内）。
- 未接続（必要スコープ無し）の read は「未接続」で非ゼロ。
- REGISTRY 拡張：gdrive が新規に、gmail/calendar のプレースホルダが実装済みとしてメニュー/
  connector read の両方に現れる。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.parse

from watari_cli import cloud, config, connectors, host
from watari_cli import google_connectors as gconn
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


class _GoogleIsolated(unittest.TestCase):
    """XDG_CONFIG_HOME を隔離し、google の client_id/secret/refresh_token を用意する。

    test_cloud.py の _Base と同じ隔離（同梱既定を空に固定し、env の WATARI_GOOGLE_* を消す）に、
    connectors 用の HTTP・authorize・prompts の差し替えを足したもの。
    """

    _ENV_KEYS = ("WATARI_GOOGLE_CLIENT_ID", "WATARI_GOOGLE_CLIENT_SECRET", "XDG_CONFIG_HOME")

    def setUp(self):
        self._cfg = tempfile.TemporaryDirectory(prefix="watari-connect-google-cfg-")
        self._saved_env = {k: os.environ.get(k) for k in self._ENV_KEYS}
        os.environ.pop("WATARI_GOOGLE_CLIENT_ID", None)
        os.environ.pop("WATARI_GOOGLE_CLIENT_SECRET", None)
        os.environ["XDG_CONFIG_HOME"] = self._cfg.name
        self._saved_bundled = (cloud._BUNDLED_CLIENT_ID, cloud._BUNDLED_CLIENT_SECRET)
        cloud._BUNDLED_CLIENT_ID = cloud._BUNDLED_CLIENT_SECRET = ""
        config.save_config(google={"client_id": "cid", "client_secret": "csec",
                                   "refresh_token": "RT", "scopes": [cloud.SCOPE]})
        self._saved_cloud_http = cloud._http
        self._saved_gconn_http = gconn._http
        self._saved_authorize = cloud.authorize
        from watari_cli import prompts
        self._saved_prompts = {"text": prompts.text, "select": prompts.select}
        # oauth 経路は貼り付けを一切要求しない契約——呼ばれたら即座に失敗させて検出する。
        prompts.text = self._unexpected_paste

        def token_router(method, url, headers=None, data=None):
            if url == cloud._TOKEN_URL:
                return 200, b'{"access_token":"AT"}'
            return 404, b"{}"
        cloud._http = token_router

    def tearDown(self):
        cloud._BUNDLED_CLIENT_ID, cloud._BUNDLED_CLIENT_SECRET = self._saved_bundled
        cloud._http = self._saved_cloud_http
        gconn._http = self._saved_gconn_http
        cloud.authorize = self._saved_authorize
        from watari_cli import prompts
        prompts.text = self._saved_prompts["text"]
        prompts.select = self._saved_prompts["select"]
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._cfg.cleanup()

    @staticmethod
    def _unexpected_paste(*a, **k):
        raise AssertionError("oauth 経路は貼り付けプロンプトを呼んではいけない")

    def _fake_authorize(self, ok=True, message="authorized", capture=None):
        """cloud.authorize を差し替える（実ブラウザ/実ループバックは通さない）。

        成功時は実装同様「drive.appdata ＋要求スコープ」を config.google.scopes に積む。
        """
        def fn(scopes=None):
            if capture is not None:
                capture.append(list(scopes or []))
            if ok:
                google = config.load_config().get("google") or {}
                granted = set(google.get("scopes") or [])
                granted.add(cloud.SCOPE)
                granted.update(scopes or [])
                google["scopes"] = sorted(granted)
                config.save_config(google=google)
            return ok, message
        cloud.authorize = fn


class ConnectWizardGmailTest(_GoogleIsolated):
    def test_missing_scope_triggers_authorize_with_required_scope_then_declares_connector(self):
        capture = []
        self._fake_authorize(capture=capture)
        gconn._http = _fake_http(lambda m, u, h, d: (
            200, json.dumps({"emailAddress": "me@example.com"}).encode())
            if "/profile" in u else (404, b"{}"))

        rc, out, err = _run(["connect", "gmail"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(capture, [[gconn.GMAIL_SCOPE]])
        self.assertIn("me@example.com", out)
        decl = config.load_connectors()
        self.assertEqual(len(decl), 1)
        self.assertEqual((decl[0]["name"], decl[0]["scope"]), ("gmail", "cloud"))

    def test_already_granted_scope_skips_authorize(self):
        config.save_config(google={"client_id": "cid", "client_secret": "csec",
                                   "refresh_token": "RT",
                                   "scopes": [cloud.SCOPE, gconn.GMAIL_SCOPE]})

        def boom(scopes=None):
            raise AssertionError("スコープ既付与のとき authorize を呼んではいけない")
        cloud.authorize = boom
        gconn._http = _fake_http(lambda m, u, h, d: (
            200, json.dumps({"emailAddress": "me@example.com"}).encode())
            if "/profile" in u else (404, b"{}"))

        rc, out, err = _run(["connect", "gmail"])
        self.assertEqual(rc, 0, err)
        self.assertIn("me@example.com", out)

    def test_authorize_failure_saves_nothing(self):
        self._fake_authorize(ok=False, message="認証されませんでした（timeout）")
        rc, out, err = _run(["connect", "gmail"])
        self.assertEqual(rc, 1)
        self.assertEqual(config.load_connectors(), [])
        self.assertIn("認証されませんでした", err)

    def test_guide_mentions_browser_approval_and_no_paste_prompt(self):
        self._fake_authorize()
        gconn._http = _fake_http(lambda m, u, h, d: (
            200, json.dumps({"emailAddress": "me@example.com"}).encode()))
        rc, out, _err = _run(["connect", "gmail"])
        self.assertEqual(rc, 0)
        self.assertIn("ブラウザ", out)  # prompts.text が呼ばれていれば setUp の AssertionError で落ちる

    def test_menu_lists_gmail_as_implemented(self):
        from watari_cli import prompts
        prompts.select = lambda *a, **k: "gmail"
        self._fake_authorize()
        gconn._http = _fake_http(lambda m, u, h, d: (
            200, json.dumps({"emailAddress": "me@example.com"}).encode()))
        rc, out, _err = _run(["connect"])
        self.assertEqual(rc, 0)
        self.assertIn("me@example.com", out)


class ConnectorReadGmailTest(_GoogleIsolated):
    def setUp(self):
        super().setUp()
        self._saved_mem = wl.MEM
        self._home = tempfile.TemporaryDirectory(prefix="watari-connread-google-home-")
        wl.MEM = self._home.name
        config.save_config(google={"client_id": "cid", "client_secret": "csec",
                                   "refresh_token": "RT",
                                   "scopes": [cloud.SCOPE, gconn.GMAIL_SCOPE]})

    def tearDown(self):
        wl.MEM = self._saved_mem
        self._home.cleanup()
        super().tearDown()

    def _message(self, mid, internal_ms, frm="a@x.com", subject="hi", snippet="body..."):
        return {
            "id": mid, "threadId": f"t-{mid}", "internalDate": str(internal_ms), "snippet": snippet,
            "payload": {"headers": [
                {"name": "From", "value": frm}, {"name": "Subject", "value": subject},
            ]},
        }

    def test_json_output_is_unified_and_ascending(self):
        # list は新しい順（Gmail の既定）で返す想定：新しい方を先に置いて、応答順に依存しないことを確認
        msgs = {"m2": self._message("m2", 1_752_800_000_000, subject="new"),
                "m1": self._message("m1", 1_752_000_000_000, subject="old")}

        def router(method, url, headers, data):
            if "/messages?" in url:
                return 200, json.dumps({"messages": [{"id": "m2"}, {"id": "m1"}]}).encode()
            for mid, msg in msgs.items():
                if f"/messages/{mid}?" in url:
                    return 200, json.dumps(msg).encode()
            return 404, b"{}"
        gconn._http = _fake_http(router)

        rc, out, err = _run(["connector", "read", "gmail", "--since",
                             "2026-01-01T00:00:00.000Z", "--json"])
        self.assertEqual(rc, 0, err)
        rows = json.loads(out)
        self.assertEqual([r["uuid"] for r in rows],
                         sorted(r["uuid"] for r in rows))  # ts 昇順
        self.assertEqual(set(rows[0].keys()), {"ts", "uuid", "text", "meta"})
        uuids = [r["uuid"] for r in rows]
        self.assertTrue(any(u.startswith("gmail:m1@") for u in uuids))
        self.assertTrue(any(u.startswith("gmail:m2@") for u in uuids))
        old_row = next(r for r in rows if r["uuid"].startswith("gmail:m1@"))
        self.assertIn("From: a@x.com", old_row["text"])
        self.assertIn("Subject: old", old_row["text"])

    def test_since_maps_to_after_epoch_seconds_query(self):
        captured = {}

        def router(method, url, headers, data):
            captured["url"] = url
            return 200, json.dumps({"messages": []}).encode()
        gconn._http = _fake_http(router)
        rc, _out, err = _run(
            ["connector", "read", "gmail", "--since", "2026-01-01T00:00:00.000Z", "--json"])
        self.assertEqual(rc, 0, err)
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(captured["url"]).query)
        self.assertTrue(qs["q"][0].startswith("after:"))

    def test_auth_error_401_is_nonzero_with_no_partial_output(self):
        gconn._http = _fake_http(lambda m, u, h, d: (401, b'{"error":"unauthorized"}'))
        rc, out, err = _run(["connector", "read", "gmail", "--since", "2026-01-01", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("認証エラー", err)

    def test_forbidden_403_mentions_scope_shortage(self):
        gconn._http = _fake_http(lambda m, u, h, d: (403, b'{"error":"insufficient scope"}'))
        rc, out, err = _run(["connector", "read", "gmail", "--since", "2026-01-01", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("スコープ不足", err)

    def test_unconnected_without_required_scope_is_rejected(self):
        config.save_config(google={"client_id": "cid", "client_secret": "csec",
                                   "refresh_token": "RT", "scopes": [cloud.SCOPE]})
        rc, out, err = _run(["connector", "read", "gmail", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("未接続", err)

    def test_since_defaults_to_host_cursor_when_omitted(self):
        host.save_cursors(self._home.name, {"gmail": "2026-01-01T00:00:00.000Z"})
        captured = {}

        def router(method, url, headers, data):
            captured["url"] = url
            return 200, json.dumps({"messages": []}).encode()
        gconn._http = _fake_http(router)
        rc, _out, err = _run(["connector", "read", "gmail", "--json"])
        self.assertEqual(rc, 0, err)
        self.assertIn("after", urllib.parse.unquote(captured["url"]))


class ConnectWizardCalendarTest(_GoogleIsolated):
    def test_missing_scope_triggers_authorize_with_required_scope(self):
        capture = []
        self._fake_authorize(capture=capture)
        gconn._http = _fake_http(lambda m, u, h, d: (
            200, json.dumps({"summary": "My Calendar", "id": "me@example.com"}).encode()))
        rc, out, err = _run(["connect", "calendar"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(capture, [[gconn.CALENDAR_SCOPE]])
        self.assertIn("My Calendar", out)
        self.assertEqual(config.load_connectors()[0]["name"], "calendar")


class ConnectorReadCalendarTest(_GoogleIsolated):
    def setUp(self):
        super().setUp()
        self._saved_mem = wl.MEM
        self._home = tempfile.TemporaryDirectory(prefix="watari-connread-calendar-home-")
        wl.MEM = self._home.name
        config.save_config(google={"client_id": "cid", "client_secret": "csec",
                                   "refresh_token": "RT",
                                   "scopes": [cloud.SCOPE, gconn.CALENDAR_SCOPE]})

    def tearDown(self):
        wl.MEM = self._saved_mem
        self._home.cleanup()
        super().tearDown()

    def _event(self, eid, updated, summary="Meeting", start="2026-07-15T10:00:00+09:00",
              status="confirmed"):
        return {"id": eid, "updated": updated, "summary": summary,
               "start": {"dateTime": start}, "status": status,
               "htmlLink": f"https://calendar.google.com/event?eid={eid}"}

    def test_json_output_is_unified_and_ascending(self):
        events = [self._event("e2", "2026-07-15T00:00:00.000Z"),
                 self._event("e1", "2026-07-10T00:00:00.000Z")]  # 応答順はわざと逆
        captured = {}

        def router(method, url, headers, data):
            captured["url"] = url
            return 200, json.dumps({"items": events}).encode()
        gconn._http = _fake_http(router)

        rc, out, err = _run(["connector", "read", "calendar", "--since",
                             "2026-07-01T00:00:00.000Z", "--json"])
        self.assertEqual(rc, 0, err)
        rows = json.loads(out)
        self.assertEqual([r["uuid"] for r in rows],
                         ["calendar:e1@2026-07-10", "calendar:e2@2026-07-15"])
        self.assertEqual(set(rows[0].keys()), {"ts", "uuid", "text", "meta"})
        self.assertIn("Meeting", rows[0]["text"])
        self.assertIn("status=confirmed", rows[0]["text"])
        self.assertIn("updatedMin=2026-07-01", captured["url"])

    def test_auth_error_is_nonzero(self):
        gconn._http = _fake_http(lambda m, u, h, d: (401, b'{"error":"unauthorized"}'))
        rc, out, err = _run(["connector", "read", "calendar", "--since", "2026-07-01", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("認証エラー", err)


class ConnectWizardGdriveTest(_GoogleIsolated):
    def test_missing_scope_triggers_authorize_with_required_scope(self):
        capture = []
        self._fake_authorize(capture=capture)
        gconn._http = _fake_http(lambda m, u, h, d: (
            200, json.dumps({"user": {"emailAddress": "me@example.com"}}).encode()))
        rc, out, err = _run(["connect", "gdrive"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(capture, [[gconn.GDRIVE_SCOPE]])
        self.assertIn("me@example.com", out)
        self.assertEqual(config.load_connectors()[0]["name"], "gdrive")


class ConnectorReadGdriveTest(_GoogleIsolated):
    def setUp(self):
        super().setUp()
        self._saved_mem = wl.MEM
        self._home = tempfile.TemporaryDirectory(prefix="watari-connread-gdrive-home-")
        wl.MEM = self._home.name
        config.save_config(google={"client_id": "cid", "client_secret": "csec",
                                   "refresh_token": "RT",
                                   "scopes": [cloud.SCOPE, gconn.GDRIVE_SCOPE]})

    def tearDown(self):
        wl.MEM = self._saved_mem
        self._home.cleanup()
        super().tearDown()

    def _file(self, fid, modified, name="doc.txt", mime="text/plain"):
        return {"id": fid, "name": name, "mimeType": mime, "modifiedTime": modified,
               "webViewLink": f"https://drive.google.com/file/{fid}"}

    def test_json_output_is_unified_and_ascending(self):
        files = [self._file("f2", "2026-07-15T00:00:00.000Z", name="B"),
                 self._file("f1", "2026-07-10T00:00:00.000Z", name="A")]
        captured = {}

        def router(method, url, headers, data):
            captured["url"] = url
            return 200, json.dumps({"files": files}).encode()
        gconn._http = _fake_http(router)

        rc, out, err = _run(["connector", "read", "gdrive", "--since",
                             "2026-07-01T00:00:00.000Z", "--json"])
        self.assertEqual(rc, 0, err)
        rows = json.loads(out)
        self.assertEqual([r["uuid"] for r in rows],
                         ["gdrive:f1@2026-07-10", "gdrive:f2@2026-07-15"])
        self.assertEqual(set(rows[0].keys()), {"ts", "uuid", "text", "meta"})
        self.assertIn("A", rows[0]["text"])
        self.assertIn("text/plain", rows[0]["text"])
        self.assertIn("modifiedTime", urllib.parse.unquote(captured["url"]))

    def test_forbidden_403_mentions_scope_shortage(self):
        gconn._http = _fake_http(lambda m, u, h, d: (403, b'{"error":"insufficient scope"}'))
        rc, out, err = _run(["connector", "read", "gdrive", "--since", "2026-07-01", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("スコープ不足", err)


class RegistryGoogleExtensionTest(_GoogleIsolated):
    def test_gmail_calendar_gdrive_are_implemented_in_registry(self):
        for name in ("gmail", "calendar", "gdrive"):
            service = connectors.get_service(name)
            self.assertIsNotNone(service)
            self.assertTrue(service.implemented, name)
            self.assertEqual(service.auth_kind, "oauth", name)

    def test_menu_includes_gdrive(self):
        from watari_cli import prompts
        captured = {}

        def fake_select(message, options, default=0):
            captured["options"] = options
            raise prompts.Cancelled
        prompts.select = fake_select
        rc, _out, _err = _run(["connect"])
        self.assertEqual(rc, 130)
        self.assertIn(("Google ドライブ", "gdrive"), captured["options"])


if __name__ == "__main__":
    unittest.main()
