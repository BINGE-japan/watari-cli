"""B002 wheel metadata and installed-entrypoint contracts."""

from __future__ import annotations

import ast
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zipfile
from email import policy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"
README = ROOT / "README.md"
PACKAGE = ROOT / "src" / "watari_cli"
CLI_INIT = PACKAGE / "cli" / "__init__.py"
VERSION = "watari 0.1.0\n"


def _snapshot(root: Path, *, exclude_git: bool = False) -> tuple[tuple[str, str, int, str], ...]:
    entries = []
    paths = root.rglob("*")
    if exclude_git:
        paths = (path for path in paths if path.relative_to(root).parts[0] != ".git")
    for path in sorted(paths):
        metadata = path.lstat()
        if stat.S_ISREG(metadata.st_mode):
            kind, value = "file", hashlib.sha256(path.read_bytes()).hexdigest()
        elif stat.S_ISDIR(metadata.st_mode):
            kind, value = "directory", ""
        elif stat.S_ISLNK(metadata.st_mode):
            kind, value = "symlink", os.readlink(path)
        else:
            kind, value = "other", ""
        entries.append((path.relative_to(root).as_posix(), kind, stat.S_IMODE(metadata.st_mode), value))
    return tuple(entries)


def _run(command: tuple[str, ...], cwd: Path, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True, timeout=60, check=False)


def _environment(home: Path) -> dict[str, str]:
    environment = {
        "HOME": str(home), "PATH": os.environ.get("PATH", os.defpath),
        "PYTHONDONTWRITEBYTECODE": "1", "UV_OFFLINE": "1", "UV_PYTHON_DOWNLOADS": "never",
    }
    for name in ("LANG", "LC_ALL", "LC_CTYPE"):
        if name in os.environ:
            environment[name] = os.environ[name]
    return environment


class EntrypointContractTests(unittest.TestCase):
    _temporary: tempfile.TemporaryDirectory[str] | None = None
    _installed: tuple[Path, dict[str, str], Path, tuple[tuple[str, str, int, str], ...]] | None = None
    _repository_snapshot: tuple[tuple[str, str, int, str], ...] | None = None

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._temporary is not None:
            cls._temporary.cleanup()

    def _installation(self) -> tuple[Path, dict[str, str], Path, tuple[tuple[str, str, int, str], ...]]:
        if self.__class__._installed is not None:
            return self.__class__._installed
        self.__class__._repository_snapshot = _snapshot(ROOT, exclude_git=True)
        self.assertFalse(PYPROJECT.is_symlink())
        self.assertFalse(CLI_INIT.is_symlink())
        cli_source = CLI_INIT.read_text(encoding="utf-8")
        ast.parse(cli_source, filename=str(CLI_INIT), feature_version=(3, 11))
        self.assertNotIn("__version__", cli_source)
        self.assertNotIn("0.1.0", cli_source)
        with PYPROJECT.open("rb") as stream:
            project = tomllib.load(stream)
        # pyproject はパッケージング契約に効くキーだけを固定する（description /
        # keywords / classifiers 等のメタデータ追加でこのテストが壊れないように）。
        self.assertEqual(
            project["build-system"],
            {"requires": ["setuptools==80.9.0"], "build-backend": "setuptools.build_meta"},
        )
        metadata = project["project"]
        self.assertEqual(metadata["name"], "watari-cli")
        self.assertEqual(metadata["version"], "0.1.0")
        self.assertEqual(metadata["readme"], "README.md")
        self.assertEqual(metadata["requires-python"], ">=3.11")
        self.assertEqual(metadata["dependencies"], [])  # 実行時依存ゼロ（オフライン契約）
        self.assertEqual(metadata["scripts"], {"watari": "watari_cli.cli:main"})
        setuptools_config = project["tool"]["setuptools"]
        self.assertEqual(setuptools_config["package-dir"], {"": "src"})
        self.assertEqual(setuptools_config["packages"], {"find": {"where": ["src"]}})
        package_data = setuptools_config["package-data"]["watari_cli"]
        self.assertIn("skill/*.md", package_data)  # SKILL.md / SCHEMA.md 同梱
        self.assertIn("skill/prompts/*.md", package_data)  # スラッシュコマンド同梱
        self.assertIn("pi/*.mjs", package_data)  # process-local TUI / 敬語ガード
        self.assertIn("pi/*.ts", package_data)  # Pi event hook
        self.assertIn("pytest", project["dependency-groups"]["dev"])
        temporary = tempfile.TemporaryDirectory(prefix="watari-b002-")
        self.__class__._temporary = temporary
        root, source, output, wheelhouse = Path(temporary.name), Path(temporary.name) / "source", Path(temporary.name) / "output", Path(temporary.name) / "wheelhouse"
        for directory in (source, output, wheelhouse):
            directory.mkdir()
        shutil.copy2(PYPROJECT, source / "pyproject.toml")
        shutil.copy2(README, source / "README.md")
        shutil.copytree(PACKAGE, source / "src" / "watari_cli")
        guard = root / "network-guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(
            "import os, socket\n"
            "class DeniedSocket(socket.socket):\n"
            "    def __new__(cls, *args, **kwargs): os._exit(97)\n"
            "socket.socket = DeniedSocket\n"
            "def deny(*args, **kwargs): os._exit(97)\n"
            "socket.create_connection = deny\n",
            encoding="utf-8",
        )
        uv = shutil.which("uv", path=_environment(Path.home())["PATH"])
        self.assertIsNotNone(uv)
        cache = _run((uv, "cache", "dir"), source, _environment(Path.home()))
        self.assertEqual(cache.returncode, 0, cache.stderr)
        cache_root = Path(cache.stdout.strip()).resolve(strict=True)
        backend, = {path.resolve(strict=True) for path in cache_root.glob("wheels-v*/pypi/setuptools/80.9.0-py3-none-any")}
        self.assertTrue(backend.is_dir() and backend.is_relative_to(cache_root))
        self.assertFalse(any(path.is_symlink() for path in backend.rglob("*")))
        Path(shutil.make_archive(str(wheelhouse / "setuptools-80.9.0-py3-none-any"), "zip", backend)).rename(wheelhouse / "setuptools-80.9.0-py3-none-any.whl")
        build_home = root / "build-home"
        build_home.mkdir()
        build_environment = _environment(build_home) | {
            "PIP_NO_INDEX": "1", "PYTHONPATH": str(guard), "UV_CACHE_DIR": str(root / "build-cache"), "UV_FIND_LINKS": str(wheelhouse), "UV_LINK_MODE": "copy",
        }
        build = _run(
            (uv, "build", "--offline", "--python", sys.executable, str(source), "--out-dir", str(output)),
            source, build_environment,
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        wheels, sdists = tuple(output.glob("*.whl")), tuple(output.glob("*.tar.gz"))
        self.assertEqual(tuple(path.name for path in wheels), ("watari_cli-0.1.0-py3-none-any.whl",))
        self.assertEqual(tuple(path.name for path in sdists), ("watari_cli-0.1.0.tar.gz",))
        wheel, dist_info = wheels[0], "watari_cli-0.1.0.dist-info"
        expected_members = {"watari_cli/__init__.py", "watari_cli/cli/__init__.py",
            "watari_cli/skill/SKILL.md", "watari_cli/skill/SCHEMA.md",
            *(f"watari_cli/skill/prompts/{name}.md"
              for name in ("remember", "organize", "profile", "forget", "goal", "watari-help")),
            "watari_cli/pi/quiet-ui.mjs", "watari_cli/pi/politeness.mjs",
            "watari_cli/pi/politeness-guard.ts",
            *(f"{dist_info}/{name}" for name in ("METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD"))}
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            members = set(names)
            self.assertEqual(len(members), len(names))
            self.assertLessEqual(expected_members, members)
            for member in members:
                path = PurePosixPath(member)
                self.assertFalse(path.is_absolute() or ".." in path.parts or "\\" in member or "\0" in member)
                self.assertTrue(member.startswith("watari_cli/") or member.startswith(f"{dist_info}/"))
                self.assertFalse({".git", "__pycache__", ".claude", ".codex", ".pi", ".env", ".ssh", ".gnupg", "id_rsa", "id_ed25519"} & set(path.parts))
                self.assertNotIn(path.suffix, {".pyc", ".pyo", ".pem", ".key", ".p12", ".pfx"})
            package_metadata = BytesParser(policy=policy.default).parsebytes(archive.read(f"{dist_info}/METADATA"))
            wheel_metadata = BytesParser(policy=policy.default).parsebytes(archive.read(f"{dist_info}/WHEEL"))
            self.assertEqual(archive.read(f"{dist_info}/entry_points.txt"), b"[console_scripts]\nwatari = watari_cli.cli:main\n")
        self.assertEqual(
            (package_metadata["Name"], package_metadata["Version"], package_metadata["Requires-Python"], package_metadata.get_all("Requires-Dist")),
            ("watari-cli", "0.1.0", ">=3.11", None),
        )
        self.assertEqual(
            (wheel_metadata["Generator"], wheel_metadata["Root-Is-Purelib"], wheel_metadata["Tag"]),
            ("setuptools (80.9.0)", "true", "py3-none-any"),
        )
        venv = root / "venv"
        install_environment = build_environment | {"UV_CACHE_DIR": str(root / "install-cache")}
        created = _run((uv, "venv", "--offline", "--no-project", "--python", sys.executable, str(venv)), root, install_environment)
        self.assertEqual(created.returncode, 0, created.stderr)
        venv_python = venv / "bin" / "python"
        installed = _run((uv, "pip", "install", "--offline", "--no-deps", "--python", str(venv_python), str(wheel)), root, install_environment)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        executable = venv / "bin" / "watari"
        self.assertTrue(executable.is_file())

        protected = root / "protected"
        protected.mkdir()
        invocation_environment = _environment(protected / "home") | {
            "PYTHONPATH": str(guard), "WATARI_HOME": str(protected / "watari-home"),
            "XDG_CACHE_HOME": str(protected / "xdg-cache"), "XDG_CONFIG_HOME": str(protected / "xdg-config"),
            "XDG_DATA_HOME": str(protected / "xdg-data"), "XDG_STATE_HOME": str(protected / "xdg-state"),
        }
        for name in ("HOME", "WATARI_HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
            Path(invocation_environment[name]).mkdir()
        probe = _run(
            (str(venv_python), "-c", "import socket; socket.socket()"),
            protected, invocation_environment,
        )
        self.assertEqual((probe.returncode, probe.stdout, probe.stderr), (97, "", ""))
        snapshot = _snapshot(protected)
        # 実CLI: status は WATARI_HOME の記憶を読むだけ。exit 0・ネットワーク無し・
        # 記憶の外へ一切書かない（protected スナップショット不変）ことを固定契約とする。
        status = _run((str(executable), "status"), protected, invocation_environment)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("記憶", status.stdout)
        self.assertEqual(status.stderr, "")
        self.assertEqual(_snapshot(protected), snapshot)
        self.assertEqual(_snapshot(ROOT, exclude_git=True), self.__class__._repository_snapshot)
        result = (executable, invocation_environment, protected, snapshot)
        self.__class__._installed = result
        return result

    def _assert_unchanged(self, protected: Path, snapshot: tuple[tuple[str, str, int, str], ...]) -> None:
        self.assertEqual(_snapshot(protected), snapshot)
        self.assertEqual(_snapshot(ROOT, exclude_git=True), self.__class__._repository_snapshot)

    def test_t_pkg_help(self) -> None:
        """T-PKG-HELP: installed --help lists the real subcommands, offline and side-effect free."""
        self.assertTrue(CLI_INIT.is_file(), "missing watari entrypoint")
        executable, environment, protected, snapshot = self._installation()
        result = _run((str(executable), "--help"), protected, environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("status", result.stdout)
        # 抽出サブコマンドが載っていること（公開名は scan。旧名 dream からの移行期間中はどちらでも可）
        self.assertTrue(
            "scan" in result.stdout or "dream" in result.stdout,
            f"--help に抽出サブコマンド（scan/dream）が見当たらない:\n{result.stdout}",
        )
        self._assert_unchanged(protected, snapshot)

    def test_t_pkg_version(self) -> None:
        """T-PKG-VERSION: installed --version is metadata-driven and side-effect free."""
        self.assertTrue(PYPROJECT.is_file(), "missing packaging metadata")
        executable, environment, protected, snapshot = self._installation()
        version = _run((str(executable), "--version"), protected, environment)
        self.assertEqual((version.returncode, version.stdout, version.stderr), (0, VERSION, ""))
        self._assert_unchanged(protected, snapshot)


if __name__ == "__main__":
    unittest.main()
