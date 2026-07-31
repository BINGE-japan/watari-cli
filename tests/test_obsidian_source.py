"""Obsidian vault を汎用shellなしで読む組み込みlocal sourceの契約テスト。"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from watari_cli import config, connectors, obsidian
from watari_cli.transcripts import common


class ObsidianSourceTest(unittest.TestCase):
    def setUp(self):
        self._cfg = tempfile.TemporaryDirectory(prefix="watari-obsidian-config-")
        self._saved_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._cfg.name
        self._vault_tmp = tempfile.TemporaryDirectory(prefix="watari-obsidian-vault-")
        self.vault = Path(self._vault_tmp.name)
        (self.vault / ".obsidian").mkdir()

    def tearDown(self):
        self._vault_tmp.cleanup()
        if self._saved_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._saved_xdg
        self._cfg.cleanup()

    def _note(self, relative: str, text: str, epoch: float) -> Path:
        note = self.vault / relative
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(text, encoding="utf-8")
        os.utime(note, (epoch, epoch))
        return note

    def test_legacy_custom_declaration_is_migrated_without_running_its_instruction(self):
        self._note("Plans.md", "A durable decision", 1_750_000_000.123456)
        config.save_connector({
            "name": "obsidian", "scope": "local",
            "read": f"Obsidian差分を読む。vault={self.vault}。findで列挙する。",
        })

        service = connectors.get_service("obsidian")
        self.assertEqual((service.auth_kind, service.scope), ("local", "local"))
        self.assertTrue(connectors.is_builtin_name("obsidian"))
        self.assertTrue(connectors.is_connected("obsidian"))
        ok, _message = obsidian.verify()
        self.assertTrue(ok)
        self.assertEqual(common.configured_path("obsidian"), str(self.vault.resolve()))
        self.assertEqual([row["text"] for row in connectors.read("obsidian", None)],
                         ["A durable decision"])

    def test_reads_markdown_only_and_excludes_internal_summary_and_symlinks(self):
        early = self._note("Projects/Alpha.md", "alpha", 1_750_000_000.100001)
        late = self._note("Journal/Daily.md", "daily", 1_750_000_100.200002)
        self._note(".obsidian/private.md", "hidden", 1_750_000_200.0)
        self._note("Journal/Watari/summary.md", "derived", 1_750_000_300.0)
        (self.vault / "not-a-note.txt").write_text("ignored", encoding="utf-8")
        try:
            (self.vault / "linked.md").symlink_to(late)
        except OSError:
            pass
        common.save_path("obsidian", str(self.vault))

        rows = obsidian.read(None)
        self.assertEqual([row["meta"]["cwd"] for row in rows],
                         ["Projects/Alpha.md", "Journal/Daily.md"])
        self.assertTrue(all(row["role"] == "user" for row in rows))
        self.assertTrue(all(row["uuid"].startswith("obsidian:") for row in rows))
        self.assertEqual([row["text"] for row in rows], ["alpha", "daily"])

        since = rows[0]["ts"]
        self.assertEqual([row["meta"]["cwd"] for row in obsidian.read(since)],
                         ["Journal/Daily.md"])
        self.assertEqual(rows[0]["ts"], obsidian.mtime_iso(early.stat().st_mtime))

    def test_home_or_filesystem_root_cannot_be_used_as_a_vault(self):
        self.assertFalse(obsidian.is_safe_vault(Path.home()))
        self.assertFalse(obsidian.is_safe_vault(Path(Path.home().anchor)))


if __name__ == "__main__":
    unittest.main()
