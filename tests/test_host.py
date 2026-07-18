"""host（マシンごとの環境記録）の契約テスト。"""
from __future__ import annotations

import json
import os
import re
import tempfile
import unittest

from watari_cli import host


TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
AUTO_FIELDS = ("machine_id", "hostname", "platform", "python", "ai_clis", "shell", "facts", "updated")


class HostRecordTest(unittest.TestCase):
    def test_refresh_creates_namespaced_file_with_auto_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="watari-host-") as home:
            record = host.refresh(home)
            # マシン名で名前空間を切ったファイルが hosts/ の下にできる
            path = host.host_path(home)
            self.assertEqual(path, os.path.join(home, "hosts", f"{host.machine_id()}.json"))
            self.assertTrue(os.path.isfile(path))
            # ファイル名（machine_id）は安全なスラッグ
            self.assertRegex(host.machine_id(), r"^[a-z0-9-]+$")
            # 自動検出フィールドが揃っている
            for field in AUTO_FIELDS:
                self.assertIn(field, record)
            self.assertEqual(record["machine_id"], host.machine_id())
            self.assertIsInstance(record["ai_clis"], list)
            self.assertIsInstance(record["facts"], dict)
            self.assertEqual(record["facts"], {})
            self.assertRegex(record["updated"], TIMESTAMP_RE)
            # ディスク上の内容と一致する
            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f), record)

    def test_set_fact_persists_and_survives_refresh(self) -> None:
        with tempfile.TemporaryDirectory(prefix="watari-host-") as home:
            host.set_fact(home, "terminal", "Ghostty")
            with open(host.host_path(home), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["facts"]["terminal"], "Ghostty")
            # 後から refresh しても facts は消えない（自動情報だけ更新される）
            record = host.refresh(home)
            self.assertEqual(record["facts"]["terminal"], "Ghostty")
            self.assertEqual(record["machine_id"], host.machine_id())

    def test_all_hosts_sees_multiple_machines(self) -> None:
        with tempfile.TemporaryDirectory(prefix="watari-host-") as home:
            host.refresh(home)  # このマシンのファイル
            # 別マシンのファイルを手で用意（他マシンが書いた状態を模す）
            other = {
                "machine_id": "darwin-othermac", "hostname": "othermac",
                "platform": "Darwin", "python": "3.12.0", "ai_clis": [],
                "shell": "zsh", "facts": {"terminal": "iTerm"},
                "updated": "2026-01-01T00:00:00.000Z",
            }
            with open(os.path.join(home, "hosts", "darwin-othermac.json"), "w", encoding="utf-8") as f:
                json.dump(other, f)
            records = host.all_hosts(home)
            self.assertEqual(len(records), 2)
            self.assertEqual({r["machine_id"] for r in records}, {host.machine_id(), "darwin-othermac"})


class HostCursorsTest(unittest.TestCase):
    """取り込みカーソルが（共有 cursors.json ではなく）このマシンの host 記録に載る契約。"""

    LEGACY = {
        "transcripts_win": "2026-07-01T10:00:00.000Z",
        "transcripts_wsl": "2026-07-02T11:00:00.000Z",
        "transcripts_codex": None, "slack": None, "gmail": None,
        "calendar": None, "linear": None, "obsidian": None,
        "last_run": "2026-07-02T12:00:00.000Z",
    }

    def test_empty_defaults_when_no_record_and_no_legacy(self) -> None:
        # host 記録も cursors.json も無ければ全キー None を返し、何も書かない
        # （status が空の記憶に対して副作用を持たない契約の要）。
        with tempfile.TemporaryDirectory(prefix="watari-cur-") as home:
            self.assertEqual(host.load_cursors(home), {k: None for k in host.CURSOR_KEYS})
            self.assertFalse(os.path.exists(host.host_path(home)))
            self.assertFalse(os.path.isdir(os.path.join(home, "hosts")))

    def test_legacy_cursors_json_migrates_into_host_record_once(self) -> None:
        with tempfile.TemporaryDirectory(prefix="watari-cur-") as home:
            legacy_path = os.path.join(home, "cursors.json")
            with open(legacy_path, "w", encoding="utf-8") as f:
                json.dump(self.LEGACY, f)
            self.assertFalse(os.path.exists(host.host_path(home)))
            # 初回読み取りで旧 cursors.json の位置を保全したまま host 記録へ移行
            self.assertEqual(host.load_cursors(home), self.LEGACY)
            with open(host.host_path(home), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["cursors"], self.LEGACY)  # 既存位置を保全
            # cursors.json は消さない（リポ外の旧ルーティンがまだ読む）
            with open(legacy_path, encoding="utf-8") as f:
                self.assertEqual(json.load(f), self.LEGACY)
            # 2回目以降は host 記録から読む（移行は一度きり）
            self.assertEqual(host.load_cursors(home), self.LEGACY)

    def test_save_cursors_advances_host_and_leaves_legacy_and_facts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="watari-cur-") as home:
            legacy_path = os.path.join(home, "cursors.json")
            with open(legacy_path, "w", encoding="utf-8") as f:
                json.dump(self.LEGACY, f)
            host.set_fact(home, "terminal", "Ghostty")  # facts を先に置く
            cursors = host.load_cursors(home)            # record 有・cursors 無 → 移行
            advanced = dict(cursors, transcripts_wsl="2026-07-10T09:00:00.000Z")
            host.save_cursors(home, advanced)
            with open(host.host_path(home), encoding="utf-8") as f:
                record = json.load(f)
            self.assertEqual(record["cursors"]["transcripts_wsl"], "2026-07-10T09:00:00.000Z")
            self.assertEqual(record["facts"]["terminal"], "Ghostty")   # facts を壊さない
            self.assertEqual(record["machine_id"], host.machine_id())  # 自動情報も揃う
            # cursors.json は正本ではないので前進の影響を受けない
            with open(legacy_path, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["transcripts_wsl"], self.LEGACY["transcripts_wsl"])


if __name__ == "__main__":
    unittest.main()
