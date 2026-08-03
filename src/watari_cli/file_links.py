"""検証済みローカルファイルをクリックから安全に開くための固定処理。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlparse

_SCHEME = "watari-file"
_VERSION = "v1"
_SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}
_SENSITIVE_TOKEN = re.compile(
    r"(?:^|[-_.])(secret|secrets|credential|credentials|token|tokens|password|passwd|"
    r"api[-_]?key|private[-_]?key)(?:$|[-_.])",
    re.IGNORECASE,
)


def file_link_key_path() -> Path:
    """OSユーザー専用のローカルリンク署名鍵の固定位置。"""
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "watari" / "file-links.key"


def ensure_file_link_key() -> Path:
    """リンク署名鍵を0600で一度だけ生成する。"""
    path = file_link_key_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "wb") as f:
            f.write(secrets.token_bytes(32))
    try:
        path.chmod(0o600)
    except OSError:
        pass
    _load_key(path)
    return path


def _load_key(path: Path | None = None) -> bytes:
    path = path or file_link_key_path()
    info = path.stat()
    current_uid = getattr(os, "getuid", lambda: None)()
    wrong_owner = current_uid is not None and getattr(info, "st_uid", current_uid) != current_uid
    if not stat.S_ISREG(info.st_mode) or wrong_owner or (os.name != "nt" and info.st_mode & 0o077):
        raise PermissionError("file link key must be an owner-only regular file")
    key = path.read_bytes()
    if len(key) != 32:
        raise ValueError("file link key must contain exactly 32 bytes")
    return key


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if stat.S_ISLNK(os.lstat(current).st_mode):
            return True
    return False


def _is_sensitive(path: Path) -> bool:
    components = [part for part in path.parts if part not in (path.anchor, os.sep)]
    if any(part.startswith(".") for part in components):
        return True
    basename = path.name.lower()
    if path.suffix.lower() in _SENSITIVE_SUFFIXES or _SENSITIVE_TOKEN.search(basename):
        return True
    lowered = "/".join(part.lower() for part in components)
    return any(marker in lowered for marker in (
        "/user data/", "/browser-profile/", "/browser_profile/", "/chrome-win/",
    ))


def _inside(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((path, root)) == str(root)
    except ValueError:
        return False


def validate_local_file(raw_path: str, *, cwd: str | None = None) -> Path:
    """表示してよい実ファイルだけを正規化して返す。"""
    if not isinstance(raw_path, str) or not raw_path or any(ord(ch) < 32 for ch in raw_path):
        raise ValueError("invalid file path")
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = Path(cwd or os.getcwd()) / candidate
    absolute = Path(os.path.abspath(candidate))
    resolved = absolute.resolve(strict=True)
    if absolute != resolved or _has_symlink_component(absolute):
        raise ValueError("symlinked paths are not linkable")

    info = resolved.stat()
    current_uid = getattr(os, "getuid", lambda: None)()
    wrong_owner = current_uid is not None and getattr(info, "st_uid", current_uid) != current_uid
    if not stat.S_ISREG(info.st_mode) or wrong_owner or info.st_nlink != 1:
        raise ValueError("only owner-controlled regular files are linkable")
    if _is_sensitive(resolved):
        raise ValueError("sensitive paths are not linkable")

    roots = [Path.home().resolve(), Path(tempfile.gettempdir()).resolve()]
    if cwd:
        roots.append(Path(cwd).resolve())
    windows_users = Path("/mnt/c/Users")
    if windows_users.is_dir():
        roots.append(windows_users.resolve())
    if not any(_inside(resolved, root) for root in roots):
        raise ValueError("file is outside allowed roots")
    return resolved


def _signature(path: str, key: bytes) -> str:
    return hmac.new(key, f"{_VERSION}\0{path}".encode(), hashlib.sha256).hexdigest()


def build_file_link(raw_path: str, *, cwd: str | None = None) -> str:
    """検証済みパスを、改ざん検知付きのHerdr専用URLにする。"""
    path = str(validate_local_file(raw_path, cwd=cwd))
    payload = base64.urlsafe_b64encode(path.encode()).decode().rstrip("=")
    return f"{_SCHEME}://open/{payload}?sig={_signature(path, _load_key())}"


def verify_file_link(url: str, *, key_path: Path | None = None) -> Path:
    """渡されたURLを検証し、現在も安全な実ファイルなら返す。"""
    parsed = urlparse(url)
    if parsed.scheme != _SCHEME or parsed.netloc != "open" or parsed.fragment:
        raise ValueError("invalid file link")
    payload = parsed.path.removeprefix("/")
    if not payload or "/" in payload:
        raise ValueError("invalid file link payload")
    query = parse_qs(parsed.query, strict_parsing=True)
    if set(query) != {"sig"} or len(query["sig"]) != 1:
        raise ValueError("invalid file link signature")
    padded = payload + "=" * (-len(payload) % 4)
    try:
        path = base64.b64decode(padded, altchars=b"-_", validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("invalid file link payload") from exc
    expected = _signature(path, _load_key(key_path))
    if not hmac.compare_digest(query["sig"][0], expected):
        raise ValueError("invalid file link signature")
    return validate_local_file(path)


def _powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def windows_file_link_command(
    distro: str,
    watari_executable: str,
    *,
    user: str | None = None,
    key_path: str | None = None,
) -> str:
    """WindowsのURL起動設定に保存する、shellを介さない固定コマンドを返す。"""
    if not distro or any(ord(ch) < 32 for ch in distro):
        raise ValueError("invalid WSL distribution name")
    executable = Path(watari_executable)
    if not executable.is_absolute() or any(ord(ch) < 32 for ch in watari_executable):
        raise ValueError("watari executable must be an absolute path")
    if user is None:
        import pwd
        user = pwd.getpwuid(os.getuid()).pw_name
    if not user or any(ord(ch) < 32 for ch in user):
        raise ValueError("invalid WSL user name")
    key = Path(key_path) if key_path else file_link_key_path()
    if not key.is_absolute() or any(ord(ch) < 32 for ch in str(key)):
        raise ValueError("file link key must have an absolute path")
    argv = [
        r"C:\Windows\System32\wsl.exe",
        "-d", distro,
        "-u", user,
        "--exec", watari_executable,
        "_open-file-link",
        "--key-path", str(key),
    ]
    # URLはShellExecuteが %1 に入れる。cmd/bashを介さずwatariの引数として直接渡す。
    return subprocess.list2cmdline(argv) + ' "%1"'


def ensure_windows_file_link_protocol(watari_executable: str | None = None) -> bool:
    """WSL利用時、watari-file URLを現在のWindowsユーザーへ登録する。"""
    distro = os.environ.get("WSL_DISTRO_NAME", "")
    if not distro:
        return False
    executable = watari_executable or shutil.which("watari")
    if not executable:
        return False
    try:
        command = windows_file_link_command(
            distro, executable, key_path=str(file_link_key_path()))
        root = r"HKCU:\Software\Classes\watari-file"
        command_key = root + r"\shell\open\command"
        script = (
            f"$root = {_powershell_literal(root)}; "
            f"$commandKey = {_powershell_literal(command_key)}; "
            f"$command = {_powershell_literal(command)}; "
            "$null = New-Item -Path $commandKey -Force; "
            "Set-Item -LiteralPath $root -Value 'URL:Watari file link'; "
            "$null = New-ItemProperty -LiteralPath $root -Name 'URL Protocol' "
            "-Value '' -PropertyType String -Force; "
            "Set-Item -LiteralPath $commandKey -Value $command"
        )
        encoded = base64.b64encode(script.encode("utf-16le")).decode()
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=True,
        )
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def reveal_file(path: Path) -> None:
    """各OSのファイル管理画面で対象ファイルを選択表示する。"""
    if os.environ.get("WSL_DISTRO_NAME"):
        converted = subprocess.run(
            ["wslpath", "-w", str(path)], capture_output=True, text=True,
            timeout=10, check=True,
        ).stdout.strip()
        argument = f'/select,"{converted}"'
        script = (
            f"$arg = {_powershell_literal(argument)}; "
            "Start-Process -FilePath 'explorer.exe' -ArgumentList $arg"
        )
        encoded = base64.b64encode(script.encode("utf-16le")).decode()
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=True,
        )
        return
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)], timeout=15, check=True)
        return
    if os.name == "nt":
        subprocess.Popen(["explorer.exe", f"/select,{path}"], close_fds=True)
        return
    subprocess.Popen(["xdg-open", str(path.parent)], close_fds=True, start_new_session=True)


def cmd_open_file_link(args=None) -> int:
    """OSまたはHerdrから渡された署名済みURLだけをファイル管理画面で開く。"""
    url = getattr(args, "url", None) or os.environ.get("HERDR_PLUGIN_CLICKED_URL", "")
    raw_key_path = getattr(args, "key_path", None)
    key_path = Path(raw_key_path) if raw_key_path else None
    try:
        path = verify_file_link(url, key_path=key_path)
        reveal_file(path)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"ファイルを開けませんでした: {exc}", file=sys.stderr)
        return 1
    return 0
