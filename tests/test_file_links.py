"""検証済みローカルファイルだけを、クリック可能なFiles欄へ出す。"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from watari_cli import file_links
from watari_cli.cli import _build_parser

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "src" / "watari_cli" / "pi" / "file-links.mjs"
EXTENSION = ROOT / "src" / "watari_cli" / "pi" / "file-links.ts"
MANIFEST = ROOT / "src" / "watari_cli" / "herdr" / "herdr-plugin.toml"


class FileLinksTest(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.TemporaryDirectory(prefix="watari-file-link-state-")
        self.files = tempfile.TemporaryDirectory(prefix="watari-file-link-files-")
        self.env = mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.state.name}, clear=False)
        self.env.start()
        self.key = file_links.ensure_file_link_key()
        self.sample = Path(self.files.name) / "report.md"
        self.sample.write_text("safe", encoding="utf-8")

    def tearDown(self):
        self.env.stop()
        self.files.cleanup()
        self.state.cleanup()

    def test_signed_link_round_trip(self):
        url = file_links.build_file_link(str(self.sample))
        self.assertTrue(url.startswith("watari-file://open/"))
        self.assertEqual(file_links.verify_file_link(url), self.sample)
        self.assertEqual(self.key.stat().st_mode & 0o077, 0)

    def test_tampered_link_is_rejected(self):
        url = file_links.build_file_link(str(self.sample))
        with self.assertRaises(ValueError):
            file_links.verify_file_link(url.replace("sig=", "sig=0", 1))

    def test_symlinks_hardlinks_hidden_and_secret_files_are_rejected(self):
        symlink = Path(self.files.name) / "alias.md"
        symlink.symlink_to(self.sample)
        hardlink = Path(self.files.name) / "hard.md"
        os.link(self.sample, hardlink)
        hidden = Path(self.files.name) / ".hidden.md"
        hidden.write_text("hidden", encoding="utf-8")
        secret = Path(self.files.name) / "api-token.txt"
        secret.write_text("not-a-real-token", encoding="utf-8")
        for candidate in (symlink, hardlink, hidden, secret):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    file_links.validate_local_file(str(candidate))

    def test_node_and_python_generate_the_same_link(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required by the Pi runtime")
        script = (
            f"import {{ buildFileLink }} from {json.dumps(HELPER.as_uri())};"
            "console.log(buildFileLink(process.argv[1], process.cwd(), process.argv[2]));"
        )
        result = subprocess.run(
            [node, "--input-type=module", "-e", script, str(self.sample), str(self.key)],
            capture_output=True, text=True, timeout=10, check=True,
        )
        self.assertEqual(result.stdout.strip(), file_links.build_file_link(str(self.sample)))

    def test_handler_revalidates_before_opening(self):
        url = file_links.build_file_link(str(self.sample))
        with mock.patch.dict(os.environ, {"HERDR_PLUGIN_CLICKED_URL": url}, clear=False), \
             mock.patch.object(file_links, "reveal_file") as reveal:
            self.assertEqual(file_links.cmd_open_file_link(), 0)
        reveal.assert_called_once_with(self.sample)

    def test_handler_accepts_url_argument_from_os_protocol(self):
        url = file_links.build_file_link(str(self.sample))
        args = SimpleNamespace(url=url, key_path=str(self.key))
        with mock.patch.dict(os.environ, {"HERDR_PLUGIN_CLICKED_URL": ""}, clear=False), \
             mock.patch.object(file_links, "reveal_file") as reveal:
            self.assertEqual(file_links.cmd_open_file_link(args), 0)
        reveal.assert_called_once_with(self.sample)

    def test_hidden_open_command_parses_os_url_and_key_path(self):
        url = file_links.build_file_link(str(self.sample))
        args = _build_parser().parse_args([
            "_open-file-link", "--key-path", str(self.key), url,
        ])
        self.assertEqual(args.url, url)
        self.assertEqual(args.key_path, str(self.key))

    def test_windows_protocol_command_invokes_watari_directly(self):
        command = file_links.windows_file_link_command(
            "Ubuntu Test",
            "/home/example user/.local/bin/watari",
            user="example user",
            key_path="/home/example user/.local/state/watari/file-links.key",
        )
        self.assertIn(
            r'C:\Windows\System32\wsl.exe -d "Ubuntu Test" -u "example user" --exec',
            command,
        )
        self.assertIn(
            r'"/home/example user/.local/bin/watari" _open-file-link --key-path '
            r'"/home/example user/.local/state/watari/file-links.key" "%1"',
            command,
        )
        self.assertNotIn("cmd.exe", command.lower())
        self.assertNotIn("powershell", command.lower())
        self.assertNotIn("bash", command.lower())

    def test_windows_protocol_registration_is_per_user_and_idempotent(self):
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}, clear=False), \
             mock.patch("shutil.which", return_value="/home/example/.local/bin/watari"), \
             mock.patch.object(subprocess, "run", return_value=completed) as run:
            self.assertTrue(file_links.ensure_windows_file_link_protocol())
        argv = run.call_args.args[0]
        self.assertEqual(argv[:3], ["powershell.exe", "-NoProfile", "-NonInteractive"])
        script = base64.b64decode(argv[-1]).decode("utf-16le")
        self.assertIn(r"HKCU:\Software\Classes\watari-file", script)
        self.assertIn("URL Protocol", script)
        self.assertIn(r"C:\Windows\System32\wsl.exe", script)
        self.assertIn('"%1"', script)
        self.assertIn("Set-Item", script)

    def test_windows_protocol_registration_is_skipped_outside_wsl(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(subprocess, "run") as run:
            self.assertFalse(file_links.ensure_windows_file_link_protocol())
        run.assert_not_called()

    def test_files_card_is_tui_only_and_uses_fixed_hyperlinks(self):
        source = EXTENSION.read_text(encoding="utf-8")
        self.assertIn('pi.registerEntryRenderer<FileCardData>(ENTRY_TYPE', source)
        self.assertIn('pi.appendEntry<FileCardData>(ENTRY_TYPE', source)
        self.assertIn('pi.on("tool_result"', source)
        self.assertIn('pi.on("agent_settled"', source)
        self.assertIn("hyperlink(currentPath, expectedUrl)", source)
        self.assertNotIn("pi.sendMessage", source)

    def test_herdr_handler_only_accepts_signed_watari_urls(self):
        manifest = MANIFEST.read_text(encoding="utf-8")
        self.assertIn('id = "watari.file-links"', manifest)
        self.assertIn('command = ["watari", "_open-file-link"]', manifest)
        self.assertIn('pattern = "^watari-file://open/', manifest)
        self.assertIn("sig=[0-9a-f]{64}", manifest)


if __name__ == "__main__":
    unittest.main()
