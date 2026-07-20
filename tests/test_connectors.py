"""connector（夢に流し込むソースの宣言）の契約テスト。

薄い宣言機構だけを固める：config への宣言(load/save・スラッグ検証)、`watari connector list/add`、
そして --advance-ext が「宣言済み connector 名」だけを受理し、カーソルをマシンごとの host 記録へ
着地させること（未宣言は拒否・原子性）。ツール固有のアダプタ（linear 等の組み込みコネクタの
`watari connect` / `watari connector read`）は tests/test_connect.py で扱う。

注: connectors は WATARI_HOME ではなく config.json（XDG_CONFIG_HOME 配下）に載る。テストは
XDG_CONFIG_HOME を一時ディレクトリへ向けて分離する。ingest は MEM を値で import するため、
--advance-ext のテストでは wl.MEM と ingest.MEM の両方を一時 home へ差し替える。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest

from watari_cli import config, host
from watari_cli.cli import _build_parser
from watari_cli.engine import ingest, watari_lib as wl


class _XdgIsolated(unittest.TestCase):
    """XDG_CONFIG_HOME を一時ディレクトリへ向け、config.json を隔離する土台。"""

    def setUp(self):
        self._cfg = tempfile.TemporaryDirectory(prefix="watari-conn-cfg-")
        self._saved_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._cfg.name

    def tearDown(self):
        if self._saved_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._saved_xdg
        self._cfg.cleanup()

    def _config_path(self):
        return os.path.join(self._cfg.name, "watari", "config.json")


class ConnectorConfigTest(_XdgIsolated):
    """config.json の connectors 宣言（load/save・スラッグ検証・同名更新）。"""

    def test_empty_when_unset(self):
        self.assertEqual(config.load_connectors(), [])

    def test_save_and_load_roundtrip(self):
        config.save_connector({"name": "mail", "scope": "cloud", "read": "cursor 以降を読む"})
        self.assertEqual(config.load_connectors(),
                         [{"name": "mail", "scope": "cloud", "read": "cursor 以降を読む"}])
        # 永続化先は config.json（記憶 home ではない）。既存の他キーは壊さない。
        with open(self._config_path(), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["connectors"][0]["name"], "mail")

    def test_preserves_other_config_keys(self):
        config.save_config(home="/some/where")
        config.save_connector({"name": "mail", "scope": "cloud", "read": "x"})
        self.assertEqual(config.load_config()["home"], "/some/where")

    def test_update_in_place_by_name(self):
        config.save_connector({"name": "mail", "scope": "cloud", "read": "v1"})
        config.save_connector({"name": "tasks", "scope": "local", "read": "t"})
        config.save_connector({"name": "mail", "scope": "local", "read": "v2"})  # 同名は更新
        connectors = config.load_connectors()
        self.assertEqual([c["name"] for c in connectors], ["mail", "tasks"])  # 位置を保つ・重複しない
        mail = next(c for c in connectors if c["name"] == "mail")
        self.assertEqual((mail["scope"], mail["read"]), ("local", "v2"))

    def test_rejects_non_slug_name(self):
        for bad in ("My Mail", "Mail", "mail_box", "mail!", ""):
            with self.assertRaises(ValueError):
                config.save_connector({"name": bad, "scope": "cloud", "read": ""})
        self.assertEqual(config.load_connectors(), [])  # 不正時は何も保存しない

    def test_rejects_bad_scope(self):
        with self.assertRaises(ValueError):
            config.save_connector({"name": "mail", "scope": "remote", "read": ""})
        self.assertEqual(config.load_connectors(), [])


class ConnectorCliTest(_XdgIsolated):
    """`watari connector list` / `watari connector add` の配線。"""

    def _run(self, argv):
        args = _build_parser().parse_args(argv)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = args.func(args)
        return rc, out.getvalue(), err.getvalue()

    def test_list_empty(self):
        rc, out, _ = self._run(["connector", "list"])
        self.assertEqual(rc, 0)
        self.assertIn("なし", out)

    def test_add_then_list(self):
        rc, out, _ = self._run(
            ["connector", "add", "--name", "tasks", "--scope", "cloud", "--read", "issue を読む"])
        self.assertEqual(rc, 0)
        self.assertEqual(config.load_connectors()[0],
                         {"name": "tasks", "scope": "cloud", "read": "issue を読む"})
        rc, out, _ = self._run(["connector", "list"])
        self.assertEqual(rc, 0)
        self.assertIn("tasks", out)
        self.assertIn("cloud", out)
        self.assertIn("issue を読む", out)

    def test_add_rejects_bad_slug_returns_2(self):
        rc, _out, err = self._run(
            ["connector", "add", "--name", "Bad Name", "--scope", "cloud", "--read", "x"])
        self.assertEqual(rc, 2)
        self.assertIn("スラッグ", err)
        self.assertEqual(config.load_connectors(), [])

    def test_add_bad_scope_is_argparse_error(self):
        # scope は argparse の choices で弾かれる（SystemExit）。宣言まで届かない。
        with self.assertRaises(SystemExit):
            self._run(["connector", "add", "--name", "mail", "--scope", "remote", "--read", "x"])


class AdvanceExtConnectorTest(_XdgIsolated):
    """--advance-ext は宣言済み connector のみ受理し、カーソルを host 記録へ着地させる。"""

    def setUp(self):
        super().setUp()  # XDG（config.json）分離
        self._saved_mem = (wl.MEM, ingest.MEM)
        self._home = tempfile.TemporaryDirectory(prefix="watari-conn-ing-")
        home = self._home.name
        wl.MEM = home
        ingest.MEM = home  # ingest は MEM を値で import するため差し替える
        for sub in ("life", "learning"):
            os.makedirs(os.path.join(home, sub), exist_ok=True)
            open(wl.log_path(sub), "w", encoding="utf-8").close()
        self.home = home

    def tearDown(self):
        wl.MEM, ingest.MEM = self._saved_mem
        self._home.cleanup()
        super().tearDown()

    def _row(self, uuid="u1", **kw):
        d = {"kind": "thread", "topic": "t", "summary": "s", "note": "n",
             "ts": "2026-07-10T00:00:00.000Z", "refs": {"uuid": uuid}}
        d.update(kw)
        return d

    def test_declared_name_accepted_and_lands_in_host_record(self):
        config.save_connector({"name": "tasks", "scope": "cloud", "read": "x"})
        ingest.apply([self._row(uuid="u1")], advance_ext=["tasks=2026-07-11T00:00:00.000Z"])
        record = json.load(open(host.host_path(self.home), encoding="utf-8"))
        # 宣言名がそのままカーソルキーになる（host 記録は任意キーを許す）
        self.assertEqual(record["cursors"]["tasks"], "2026-07-11T00:00:00.000Z")
        self.assertIn("last_run", record["cursors"])

    def test_undeclared_name_rejected_and_writes_nothing(self):
        # connector 未宣言 → "ghost" は不許可。原子性で何も書かない。
        with self.assertRaises(ValueError) as cm:
            ingest.apply([self._row(uuid="u1")], advance_ext=["ghost=2026-07-11T00:00:00.000Z"])
        self.assertTrue(any("connector" in e for e in cm.exception.args[0]))
        self.assertEqual(wl.load_log("life"), [])
        self.assertFalse(os.path.exists(host.host_path(self.home)))


if __name__ == "__main__":
    unittest.main()
