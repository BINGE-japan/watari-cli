"""Safe self-update for ``watari chat`` installations created by ``uv tool``.

The documented installation keeps a local git checkout and installs the tool from
that directory.  Only a clean checkout on ``main`` is fast-forwarded to
``origin/main``.  A failed reinstall rolls the checkout back so the next launch
can retry instead of leaving source and installed code out of sync.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from importlib import metadata
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

NOTICE_ENV = "WATARI_UPDATE_NOTICE"
DISABLE_ENV = "WATARI_NO_AUTO_UPDATE"


@dataclass
class UpdateResult:
    status: str
    before: str | None = None
    after: str | None = None
    changes: list[str] = field(default_factory=list)
    reason: str | None = None
    error: str | None = None


def _run(command: list[str], *, timeout: int = 15, **kwargs) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", "ssh -oBatchMode=yes")
    try:
        return subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            check=False, env=env, **kwargs)
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(command, 124, "", str(error))


def source_checkout_from_direct_url(direct_url: dict | None) -> Path | None:
    """Resolve a local PEP 610 source URL, accepting only an existing git checkout."""
    if not isinstance(direct_url, dict):
        return None
    parsed = urlparse(str(direct_url.get("url") or ""))
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        return None
    raw_path = url2pathname(unquote(parsed.path))
    source = Path(raw_path).resolve()
    return source if source.is_dir() and (source / ".git").exists() else None


def installed_source_checkout() -> Path | None:
    try:
        raw = metadata.distribution("watari-cli").read_text("direct_url.json")
        direct_url = json.loads(raw) if raw else None
    except (metadata.PackageNotFoundError, json.JSONDecodeError, OSError):
        return None
    return source_checkout_from_direct_url(direct_url)


def _successful(result: subprocess.CompletedProcess) -> bool:
    return result.returncode == 0


def _text(result: subprocess.CompletedProcess) -> str:
    return (result.stdout or "").strip()


def update_checkout(source: Path, *, run=_run, git: str = "git", uv: str = "uv") -> UpdateResult:
    """Fast-forward a clean main checkout and reinstall its uv tool atomically enough to retry."""
    source = Path(source)
    base = [git, "-C", str(source)]

    branch = run([*base, "branch", "--show-current"])
    if not _successful(branch) or _text(branch) != "main":
        return UpdateResult("skipped", reason="branch")

    dirty = run([*base, "status", "--porcelain"])
    if not _successful(dirty):
        return UpdateResult("unavailable", reason="status", error=dirty.stderr)
    if _text(dirty):
        return UpdateResult("skipped", reason="dirty")

    current = run([*base, "rev-parse", "HEAD"])
    if not _successful(current):
        return UpdateResult("unavailable", reason="revision", error=current.stderr)
    before = _text(current)

    fetched = run([*base, "fetch", "--quiet", "origin", "main"], timeout=10)
    if not _successful(fetched):
        return UpdateResult("unavailable", before=before, reason="fetch", error=fetched.stderr)

    remote_ref = "refs/remotes/origin/main"
    remote = run([*base, "rev-parse", remote_ref])
    if not _successful(remote):
        return UpdateResult("unavailable", before=before, reason="remote", error=remote.stderr)
    after = _text(remote)
    if before == after:
        return UpdateResult("current", before=before, after=after)

    ancestor = run([*base, "merge-base", "--is-ancestor", before, after])
    if not _successful(ancestor):
        return UpdateResult("skipped", before=before, after=after, reason="diverged")

    log = run([*base, "log", "--reverse", "--format=%s", f"{before}..{after}"])
    changes = [line.strip() for line in _text(log).splitlines() if line.strip()] if _successful(log) else []

    merged = run([*base, "merge", "--ff-only", after])
    if not _successful(merged):
        return UpdateResult(
            "failed", before=before, after=after, changes=changes,
            reason="merge", error=merged.stderr)

    installed = run(
        [uv, "tool", "install", "--force", "--refresh", str(source)], timeout=180)
    if not _successful(installed):
        run([*base, "reset", "--hard", before])
        return UpdateResult(
            "failed", before=before, after=after, changes=changes,
            reason="install", error=installed.stderr)

    return UpdateResult("updated", before=before, after=after, changes=changes)


def _is_running_from_uv_tool(uv: str, *, run=_run) -> bool:
    result = run([uv, "tool", "dir"])
    if not _successful(result) or not _text(result):
        return False
    try:
        Path(sys.executable).resolve().relative_to(Path(_text(result)).resolve())
        return True
    except ValueError:
        return False


def update_installed_tool(*, run=_run) -> UpdateResult:
    """Update only the documented local-checkout + uv-tool installation shape."""
    if os.environ.get(DISABLE_ENV) == "1":
        return UpdateResult("skipped", reason="disabled")
    source = installed_source_checkout()
    git = shutil.which("git")
    uv = shutil.which("uv")
    if source is None or not git or not uv:
        return UpdateResult("skipped", reason="unsupported")
    if not _is_running_from_uv_tool(uv, run=run):
        return UpdateResult("skipped", reason="unsupported")
    return update_checkout(source, run=run, git=git, uv=uv)


def notice_lines(result: UpdateResult) -> list[str]:
    before = (result.before or "?")[:7]
    after = (result.after or "?")[:7]
    lines = [f"ワタリを更新しました（{before} → {after}）。"]
    shown = result.changes[:10]
    lines.extend(f"  ・{change}" for change in shown)
    if len(result.changes) > len(shown):
        lines.append(f"  ・ほか {len(result.changes) - len(shown)} 件")
    if not result.changes:
        lines.append("  ・main の最新版を反映しました")
    return lines


def encode_notice(result: UpdateResult) -> str:
    return json.dumps(asdict(result), ensure_ascii=False, separators=(",", ":"))


def restart_with_notice(result: UpdateResult, *, executable: str | None = None,
                        argv: list[str] | None = None, exec_fn=os.execvpe) -> bool:
    """Replace this process with the newly installed watari and carry one update notice."""
    executable = executable or shutil.which("watari")
    if not executable:
        return False
    argv = list(argv or sys.argv)
    restarted_argv = [executable, *argv[1:]]
    env = dict(os.environ)
    env[NOTICE_ENV] = encode_notice(result)
    exec_fn(executable, restarted_argv, env)
    return True  # pragma: no cover - os.execvpe does not return on success


def consume_notice() -> UpdateResult | None:
    raw = os.environ.pop(NOTICE_ENV, None)
    if not raw:
        return None
    try:
        value = json.loads(raw)
        return UpdateResult(**value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
