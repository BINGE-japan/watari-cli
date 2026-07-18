"""未初期化ホーム(watari init/install 前)に対する CLI エラーメッセージの契約テスト。

`watari ingest`/`watari regen` は、記憶(WATARI_HOME)側の life/learning/log.jsonl が
無いだけの状態でも、エンジンが投げる素の FileNotFoundError をそのまま漏らさない
（誤帰属した文言や生トレースバックを見せない）——「記憶が見つかりません」と案内し、
きれいな non-zero exit で終える契約を固める。

注: watari_lib.MEM / ingest.MEM はモジュール定数（import 時に一度だけ解決）なので、
config.apply の環境変数越しでは既に import 済みのこれらへ反映されない（他の engine
テストと同じ理由）。cmd_ingest/cmd_regen 自体（try/except とメッセージ）を運動させる
ため、他のテストと同じやり方で wl.MEM / ingest.MEM を直接差し替える。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest

from watari_cli.cli import _build_parser
from watari_cli.engine import ingest, watari_lib as wl


def _run(argv):
    args = _build_parser().parse_args(argv)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = args.func(args)
    return rc, out.getvalue(), err.getvalue()


class UninitializedHomeErrorTest(unittest.TestCase):
    """<home> はディレクトリとして存在するが watari init/install していない
    （life/learning/log.jsonl が無い）ケース。"""

    def setUp(self):
        self._saved = (wl.MEM, ingest.MEM)
        self._tmp = tempfile.TemporaryDirectory(prefix="watari-noinit-")
        home = self._tmp.name  # わざと life/learning を作らない＝未初期化を模す
        wl.MEM = home
        ingest.MEM = home

    def tearDown(self):
        wl.MEM, ingest.MEM = self._saved
        self._tmp.cleanup()

    def test_ingest_reports_missing_memory_not_missing_rows(self):
        rows_path = os.path.join(self._tmp.name, "rows.json")
        with open(rows_path, "w", encoding="utf-8") as f:
            json.dump([], f)
        rc, _out, err = _run(["ingest", "--rows", rows_path])
        self.assertEqual(rc, 1)
        self.assertIn("記憶が見つかりません", err)
        self.assertIn(wl.MEM, err)
        self.assertIn("init", err)          # watari init / watari install の案内を含む
        self.assertNotIn("rows ファイル", err)  # rows 自体は読めている＝誤帰属しない

    def test_ingest_dry_run_also_reports_missing_memory(self):
        # --dry-run でも validate() が既存 domain を読みに行くため同じ経路を通る。
        rows_path = os.path.join(self._tmp.name, "rows.json")
        with open(rows_path, "w", encoding="utf-8") as f:
            json.dump([], f)
        rc, _out, err = _run(["ingest", "--rows", rows_path, "--dry-run"])
        self.assertEqual(rc, 1)
        self.assertIn("記憶が見つかりません", err)

    def test_regen_reports_missing_memory_cleanly(self):
        rc, _out, err = _run(["regen"])
        self.assertEqual(rc, 1)
        self.assertIn("記憶が見つかりません", err)
        self.assertIn(wl.MEM, err)
        self.assertIn("init", err)

    def test_regen_check_reports_missing_memory_cleanly(self):
        rc, _out, err = _run(["regen", "--check"])
        self.assertEqual(rc, 1)
        self.assertIn("記憶が見つかりません", err)


class MissingRowsFileStillReportsRowsTest(unittest.TestCase):
    """rows 側の欠落は記憶とは無関係の原因なので、従来どおり区別して報告する。"""

    def setUp(self):
        self._saved = (wl.MEM, ingest.MEM)
        self._tmp = tempfile.TemporaryDirectory(prefix="watari-ready-")
        home = self._tmp.name
        wl.MEM = home
        ingest.MEM = home
        for sub in ("life", "learning"):  # 今度はちゃんと初期化しておく
            os.makedirs(os.path.join(home, sub), exist_ok=True)
            open(wl.log_path(sub), "w", encoding="utf-8").close()

    def tearDown(self):
        wl.MEM, ingest.MEM = self._saved
        self._tmp.cleanup()

    def test_missing_rows_file_on_initialized_home_is_a_rows_error(self):
        rc, _out, err = _run(
            ["ingest", "--rows", os.path.join(self._tmp.name, "no-such-rows.json")])
        self.assertEqual(rc, 2)
        self.assertIn("rows ファイルが読めません", err)
        self.assertNotIn("記憶が見つかりません", err)


if __name__ == "__main__":
    unittest.main()
