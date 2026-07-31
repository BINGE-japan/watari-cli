"""Watari のローカル設定に保存する秘密情報のファイル権限を固定する。"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from watari_cli import config


@unittest.skipIf(os.name == "nt", "POSIX mode bits are not a Windows security boundary")
class ConfigPermissionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="watari-config-security-")
        self._saved = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._tmp.name

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._saved
        self._tmp.cleanup()

    def test_new_config_is_owner_only_even_with_permissive_umask(self):
        old_umask = os.umask(0)
        try:
            config.save_config(secret_for_test="synthetic-only")
        finally:
            os.umask(old_umask)

        directory = Path(self._tmp.name) / "watari"
        file = directory / "config.json"
        self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)

    def test_rewrite_repairs_existing_permissive_modes(self):
        directory = Path(self._tmp.name) / "watari"
        directory.mkdir(mode=0o777)
        file = directory / "config.json"
        file.write_text('{}\n', encoding="utf-8")
        os.chmod(directory, 0o755)
        os.chmod(file, 0o644)

        config.save_config(secret_for_test="synthetic-only")

        self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)


if __name__ == "__main__":
    unittest.main()
