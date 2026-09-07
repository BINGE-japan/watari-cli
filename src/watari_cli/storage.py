"""Local durable writes and reentrant cross-process locks (no network or model calls).

Locks live outside the memory Git tree. A pending memory transaction is a redo
journal: once durable, its prevalidated files are replayed before the next read.
Unknown journals fail closed. Never sync the journal or temporary files to Git.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading

_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}
_LOCAL = threading.local()
JOURNAL = ".watari-pending.json"
_TARGET = re.compile(r"(?:(?:life|learning)/(?:log\.jsonl|state\.json)|hosts/[a-z0-9-]+\.json)\Z")


@contextmanager
def file_lock(resource, *, create=True):
    key = os.path.realpath(resource)
    with _GUARD:
        lock = _LOCKS.setdefault(key, threading.RLock())
    with lock:
        held = getattr(_LOCAL, "held", None)
        if held is None:
            held = _LOCAL.held = set()
        if key in held:
            yield
            return
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "watari/locks"
        if create:
            base.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = hashlib.sha256(key.encode()).hexdigest() + ".lock"
        try:
            fd = os.open(base / name, os.O_RDWR | (os.O_CREAT if create else 0) | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except FileNotFoundError:
            if create:
                raise
            yield
            return
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"0")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX)
            held.add(key)
            try:
                yield
            finally:
                held.remove(key)
        finally:
            os.close(fd)


def locked_home(function):
    @wraps(function)
    def locked(home, *args, **kwargs):
        with file_lock(home):
            recover(home)
            return function(home, *args, **kwargs)
    return locked


def read_home(function):
    @wraps(function)
    def locked(home, *args, **kwargs):
        with file_lock(home, create=False):
            recover(home)
            return function(home, *args, **kwargs)
    return locked


def sync_directory(path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic_write_text(path, text):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".watari-tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=1, allow_nan=False) + "\n"


def _validated_updates(home, payload):
    if not isinstance(payload, dict) or type(payload.get("version")) is not int or payload["version"] != 1:
        raise RuntimeError("未対応の保存処理のため、記憶への書き込みを停止しました。")
    updates = payload.get("files")
    if not isinstance(updates, dict) or not updates:
        raise RuntimeError("保存処理の内容を確認できません。")
    root = Path(home).resolve()
    for name, text in updates.items():
        path = root / name
        if not _TARGET.fullmatch(name) or not isinstance(text, str) or path.resolve() != path:
            raise RuntimeError("保存処理に許可されていないファイルが含まれています。")
    return updates


def recover(home):
    if not (Path(home) / JOURNAL).exists():
        return
    with file_lock(home):
        journal = Path(home) / JOURNAL
        if not journal.exists():
            return
        if journal.is_symlink():
            raise RuntimeError("保存処理のファイルを確認できません。")
        payload = json.loads(journal.read_text(encoding="utf-8"))
        updates = _validated_updates(home, payload)
        for name, text in updates.items():
            path = Path(home) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, text)
        journal.unlink()
        sync_directory(home)


def commit_files(home, updates):
    """Caller holds the memory lock and has validated/derived ALL output first."""
    with file_lock(home):
        recover(home)
        payload = {"version": 1, "files": updates}
        _validated_updates(home, payload)
        atomic_write_text(Path(home) / JOURNAL, json_text(payload))
        recover(home)
