"""Repository-shape contract for B001 (T-REPO-SHAPE)."""

from __future__ import annotations

import ast
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_INIT = REPOSITORY_ROOT / "src" / "watari_cli" / "__init__.py"
TEST_INIT = REPOSITORY_ROOT / "tests" / "__init__.py"


class ShapeContractError(AssertionError):
    """A required repository path has a missing or unsafe shape."""


def require_plain_file(path: Path, label: str) -> None:
    """Accept only an existing, non-symlink regular file."""

    if path.is_symlink():
        raise ShapeContractError(f"unexpected {label} shape: symlink")
    try:
        mode = path.stat().st_mode
    except FileNotFoundError as error:
        raise ShapeContractError(f"missing {label}: {path}") from error
    if not stat.S_ISREG(mode):
        raise ShapeContractError(f"unexpected {label} shape: not a regular file")


def require_plain_directory(path: Path, label: str) -> None:
    """Accept only an existing, non-symlink directory."""

    if path.is_symlink():
        raise ShapeContractError(f"unexpected {label} shape: symlink")
    try:
        mode = path.stat().st_mode
    except FileNotFoundError as error:
        raise ShapeContractError(f"missing {label}: {path}") from error
    if not stat.S_ISDIR(mode):
        raise ShapeContractError(f"unexpected {label} shape: not a directory")


def relative_tree(root: Path) -> tuple[str, ...]:
    """Return a stable, content-free view of paths below a synthetic root."""

    return tuple(sorted(path.relative_to(root).as_posix() for path in root.rglob("*")))


class RepoShapeTest(unittest.TestCase):
    def test_t_repo_shape(self) -> None:
        """T-REPO-SHAPE: keep the initial package inert and Python 3.11-safe."""

        expected_paths = (
            "src/watari_cli/__init__.py",
            "tests/__init__.py",
        )
        actual_paths = (
            PACKAGE_INIT.relative_to(REPOSITORY_ROOT).as_posix(),
            TEST_INIT.relative_to(REPOSITORY_ROOT).as_posix(),
        )
        self.assertEqual(actual_paths, expected_paths)

        with tempfile.TemporaryDirectory(prefix="watari-b001-shape-") as temp:
            synthetic_root = Path(temp)
            missing = synthetic_root / "missing.py"
            with self.assertRaisesRegex(ShapeContractError, "missing synthetic file"):
                require_plain_file(missing, "synthetic file")

            unexpected = synthetic_root / "unexpected.py"
            unexpected.mkdir()
            with self.assertRaisesRegex(ShapeContractError, "unexpected synthetic file shape"):
                require_plain_file(unexpected, "synthetic file")

        require_plain_file(TEST_INIT, "test init")
        require_plain_file(PACKAGE_INIT, "package init")
        require_plain_directory(PACKAGE_INIT.parent, "package root")
        require_plain_directory(PACKAGE_INIT.parent.parent, "src root")
        require_plain_directory(TEST_INIT.parent, "test root")

        for source_path in (PACKAGE_INIT, TEST_INIT):
            source = source_path.read_text(encoding="utf-8")
            try:
                ast.parse(source, filename=str(source_path), feature_version=(3, 11))
            except SyntaxError as error:
                self.fail(f"not valid Python 3.11 grammar: {source_path}: {error}")

        with tempfile.TemporaryDirectory(prefix="watari-b001-home-") as temp_home:
            home = Path(temp_home)
            before = relative_tree(home)
            import_program = "\n".join(
                (
                    "import socket",
                    "import sys",
                    f"sys.path.insert(0, {str(PACKAGE_INIT.parent.parent)!r})",
                    "def deny_network(*args, **kwargs):",
                    "    raise RuntimeError('network access during package import')",
                    "socket.socket = deny_network",
                    "socket.create_connection = deny_network",
                    "import watari_cli",
                    "for name in ('__version__', 'main', 'cli'):",
                    "    if hasattr(watari_cli, name):",
                    "        raise SystemExit(f'unexpected package behavior: {name}')",
                )
            )
            environment = {
                "HOME": str(home),
                "WATARI_HOME": str(home / "watari"),
            }
            result = subprocess.run(
                (sys.executable, "-I", "-B", "-c", import_program),
                cwd=home,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(relative_tree(home), before)


if __name__ == "__main__":
    unittest.main()
