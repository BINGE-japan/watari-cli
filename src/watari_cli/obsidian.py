"""Obsidian vault connector (local, read-only, no shell or arbitrary read instruction).

Only Markdown files below one explicitly configured vault are exposed. Obsidian's own
configuration, Watari's derived journal, dot-directories and symlinks are excluded.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re

from watari_cli import config, prompts
from watari_cli.transcripts import common

NAME = "obsidian"
LABEL = "Obsidian"
MAX_ROWS = 100
MAX_TOTAL_CHARS = 48_000
MAX_NOTE_BYTES = 64_000
_LEGACY_VAULT = re.compile(r"\bvault=([^。\r\n]+)")


def default_root() -> str:
    configured = os.environ.get("WATARI_OBSIDIAN_VAULT")
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    return os.path.expanduser("~/Documents/Obsidian")


def is_safe_vault(root: str | os.PathLike[str]) -> bool:
    try:
        candidate = Path(root).expanduser().resolve()
        home = Path.home().resolve()
    except (OSError, RuntimeError):
        return False
    if candidate == Path(candidate.anchor) or candidate == home:
        return False
    protected = (
        home / ".config", home / ".ssh", home / ".pi", home / ".claude",
        home / ".codex", home / ".local" / "share" / "watari",
    )
    return not any(candidate == item or item in candidate.parents for item in protected)


def _legacy_declared_root() -> str | None:
    """Read the old custom `vault=/path。...` declaration only for one-time migration.

    A legacy path is accepted only when it is an actual Obsidian vault (`.obsidian`
    exists), so arbitrary free-form instructions never become a generic filesystem read.
    """
    for declaration in config.load_connectors():
        if declaration.get("name") != NAME:
            continue
        match = _LEGACY_VAULT.search(str(declaration.get("read") or ""))
        if not match:
            return None
        candidate = Path(match.group(1).strip()).expanduser()
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError):
            return None
        if (is_safe_vault(resolved) and resolved.is_dir()
                and (resolved / ".obsidian").is_dir()):
            return str(resolved)
    return None


def configured_root() -> str | None:
    explicit = common.configured_path(NAME)
    if explicit:
        candidate = Path(explicit).expanduser()
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError):
            return None
        if is_safe_vault(resolved) and resolved.is_dir():
            return str(resolved)
        return None
    return _legacy_declared_root()


def _excluded(relative: Path) -> bool:
    parts = relative.parts
    if any(part.startswith(".") for part in parts):
        return True
    return len(parts) >= 2 and parts[0] == "Journal" and parts[1] == "Watari"


def _iter_notes(root: str) -> list[Path]:
    base = Path(root).resolve()
    notes: list[Path] = []
    for directory, dirnames, filenames in os.walk(base, followlinks=False):
        current = Path(directory)
        relative_dir = current.relative_to(base)
        dirnames[:] = [
            name for name in dirnames
            if not _excluded(relative_dir / name) and not (current / name).is_symlink()
        ]
        for filename in filenames:
            path = current / filename
            relative = path.relative_to(base)
            if path.suffix.lower() != ".md" or _excluded(relative) or path.is_symlink():
                continue
            notes.append(path)
    return sorted(notes, key=lambda item: item.relative_to(base).as_posix())


def count_notes(root: str) -> int:
    if not is_safe_vault(root) or not Path(root).is_dir():
        return 0
    return len(_iter_notes(root))


def is_connected() -> bool:
    return configured_root() is not None


def verify() -> tuple[bool, str]:
    candidate = configured_root()
    if candidate and count_notes(candidate):
        common.save_path(NAME, candidate)
        return True, f"{LABEL} vault を見つけました（{candidate} / Markdown {count_notes(candidate)} 件）"

    fallback = default_root()
    if is_safe_vault(fallback) and count_notes(fallback):
        resolved = str(Path(fallback).resolve())
        common.save_path(NAME, resolved)
        return True, f"{LABEL} vault を見つけました（{resolved} / Markdown {count_notes(resolved)} 件）"

    print(f"{LABEL} vault が既定の場所（{fallback}）に見つかりませんでした。")
    entered = prompts.text("Obsidian vault のフォルダを入力してください（空 Enter で中止）")
    if not entered:
        return False, "Obsidian: パスが入力されなかったため中止しました"
    resolved = str(Path(entered).expanduser().resolve())
    if not is_safe_vault(resolved) or not Path(resolved).is_dir():
        return False, f"安全に読めるObsidian vaultではありません: {resolved}"
    count = count_notes(resolved)
    if count == 0:
        return False, f"{resolved} にMarkdownノートが見つかりませんでした"
    common.save_path(NAME, resolved)
    return True, f"{LABEL} vault を見つけました（{resolved} / Markdown {count} 件）"


def mtime_iso(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def _parse_since(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _read_note(path: Path) -> tuple[str, float] | None:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            modified = os.fstat(handle.fileno()).st_mtime
            raw = handle.read(MAX_NOTE_BYTES + 1)
    except OSError:
        return None
    truncated = len(raw) > MAX_NOTE_BYTES
    text = raw[:MAX_NOTE_BYTES].decode("utf-8", errors="replace").strip()
    if not text:
        return None
    if truncated:
        text += "\n\n[長いノートのため、この位置で省略]"
    return text, modified


def read(since: str | None) -> list[dict]:
    root = configured_root()
    if not root:
        return []
    base = Path(root).resolve()
    cutoff = _parse_since(since)
    rows: list[dict] = []
    for path in _iter_notes(root):
        read_result = _read_note(path)
        if read_result is None:
            continue
        text, modified = read_result
        if cutoff is not None and modified <= cutoff:
            continue
        relative = path.relative_to(base).as_posix()
        ts = mtime_iso(modified)
        rows.append({
            "ts": ts,
            "uuid": f"{NAME}:{relative}@{ts}",
            "text": text,
            "meta": {"cwd": relative, "modified": ts},
            "role": "user",
        })
    rows.sort(key=lambda row: (row["ts"], row["uuid"]))

    selected: list[dict] = []
    chars = 0
    for row in rows:
        if selected and ((len(selected) >= MAX_ROWS or chars + len(row["text"]) > MAX_TOTAL_CHARS)
                         and row["ts"] != selected[-1]["ts"]):
            break
        selected.append(row)
        chars += len(row["text"])
    return selected
