"""MCP-first setup. Pi MCP Adapter owns transports, OAuth, tools and secure token storage.

Network/auth are intentionally delegated to its interactive setup, not duplicated in Python.
Inspection only calls its public config/metadata exports, which do not connect servers.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from urllib.parse import urlsplit

from . import storage

ADAPTER_INSTALL = 'pi install npm:pi-mcp-adapter@2.37.0'


class ConnectionError(ValueError):
    pass


def adapter_root() -> Path | None:
    agent = Path(os.environ.get('PI_CODING_AGENT_DIR') or Path.home() / '.pi/agent')
    candidates = [agent / 'npm/node_modules/pi-mcp-adapter']
    executable = shutil.which('pi-mcp-adapter')
    if executable:
        candidates.append(Path(executable).resolve().parent)
    for root in candidates:
        try:
            package = json.loads((root / 'package.json').read_text())
            version = tuple(int(p) for p in package['version'].split('.'))
            if package.get('name') == 'pi-mcp-adapter' and version >= (2, 37, 0) and (root / 'index.ts').is_file():
                return root.resolve()
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def shared_config_path() -> Path:
    # Adapter's documented shared-global path is HOME/.config, not XDG_CONFIG_HOME.
    return Path.home() / '.config/mcp/mcp.json'


def validate_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme == 'https' and parsed.hostname and parsed.port in (None, 443)
                 and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
                 and not any(c in url for c in ('$', '{', '}', '\\'))
                 and not any(ord(c) < 33 or ord(c) == 127 for c in url) and len(url) <= 2048)
    except ValueError:
        valid = False
    if not valid:
        raise ConnectionError('認証情報・変数・クエリを含まないHTTPSのMCP URLを指定してください。ローカルMCPは接続画面で設定できます。')
    return url


def register_remote(name: str, url: str) -> None:
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,62}', name):
        raise ConnectionError('接続名は小文字の英字で始まる英数字とハイフンで指定してください。')
    validate_url(url)
    path = shared_config_path()
    # Reject links before taking a lock (also refuse a linked parent).
    if path.is_symlink() or path.parent.is_symlink():
        raise ConnectionError('リンクされた接続設定は変更できません。')
    path = path.parent.resolve() / path.name
    with storage.file_lock(str(path)):
        try:
            raw = b'{}'
            if path.exists():
                fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 1024 * 1024: raise ValueError
                    with os.fdopen(fd, 'rb', closefd=False) as stream: raw = stream.read(1024 * 1024 + 1)
                finally:
                    os.close(fd)
            if len(raw) > 1024 * 1024: raise ValueError
            value = json.loads(raw)
            if not isinstance(value, dict) or not isinstance(value.get('mcpServers', {}), dict): raise ValueError
            if 'schema_version' in value or 'mcp-servers' in value: raise ValueError
        except (OSError, ValueError):
            raise ConnectionError('既存の接続設定を安全に読み取れません。watari connect の接続画面で編集してください。') from None
        servers = value.setdefault('mcpServers', {})
        if name in servers:
            if isinstance(servers[name], dict) and servers[name].get('url') == url:
                return
            raise ConnectionError('同じ名前の接続が存在します。別名を指定するか接続画面で確認してください。')
        servers[name] = {'url': url, 'lifecycle': 'lazy', 'approveTools': True}
        # Default server-driven model calls off; do not change an existing explicit policy.
        settings = value.setdefault('settings', {})
        if not isinstance(settings, dict): raise ConnectionError('接続設定の形式が不正です。')
        settings.setdefault('sampling', False)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        storage.atomic_write_text(str(path), storage.json_text(value))


def inventory(cwd: str | None = None) -> dict:
    root, node = adapter_root(), shutil.which('node')
    if root is None or node is None:
        return {'available': False, 'servers': [], 'message': ADAPTER_INSTALL}
    helper = Path(__file__).parent / 'pi/mcp-inspect.mjs'
    try:
        result = subprocess.run([node, str(helper), str(root), cwd or os.getcwd()],
                                capture_output=True, timeout=15, check=False)
        if result.returncode or len(result.stdout) > 2 * 1024 * 1024: raise ValueError
        value = json.loads(result.stdout)
        if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1: raise ValueError
        return {**value, 'available': True}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'available': True, 'servers': [], 'error': 'MCP設定を確認できません。watari connect で確認してください。'}


def launch_setup(command: str = '/mcp setup') -> int:
    from .cli import _runtime_base
    root = adapter_root()
    if root is None:
        print(f'MCP接続にはPi MCP Adapter 2.37.0以降が必要です。\n  {ADAPTER_INSTALL}\n導入後に watari connect をもう一度実行してください。', file=sys.stderr)
        return 2
    helper = Path(__file__).parent / 'pi/connect-ui.ts'
    env = {**os.environ, 'WATARI_CONNECT_COMMAND': command, 'WATARI_PYTHON': sys.executable}
    argv = [*_runtime_base('pi'), '--no-session', '--no-extensions', '--no-skills',
            '--no-prompt-templates', '--no-tools', '--extension', str(root / 'index.ts'),
            '--extension', str(helper)]
    print('MCP接続画面を開きます。入力済みのコマンドをEnterで実行してください。終了はCtrl+Dです。', flush=True)
    try:
        return subprocess.run(argv, env=env, check=False).returncode
    except KeyboardInterrupt:
        return 130
    except OSError:
        print('Piを起動できません。Piの導入状態を確認してください。', file=sys.stderr)
        return 2


def connect(args) -> int:
    if getattr(args, 'list', False):
        print(json.dumps(inventory(), ensure_ascii=False, indent=2))
        return 0
    from . import prompts
    name, url = args.service, getattr(args, 'url', None)
    try:
        if name and name.startswith('https://'):
            url, name = name, None
        if url:
            validate_url(url)
            name = name or prompts.text('接続名（例: team-docs）')
            if adapter_root() is None: return launch_setup()
            current = inventory()
            if current.get('error'): raise ConnectionError(current['error'])
            if any(s.get('name') == name for s in current.get('servers', [])):
                raise ConnectionError('同じ名前のMCP接続が既に設定されています。watari connect の接続画面で確認してください。')
            print(f'MCP接続先: {url}\n接続名: {name}\n保存先: {shared_config_path()}')
            if not prompts.confirm('この接続を登録して認証画面を開きますか？', default=False): return 0
            register_remote(name, url)
            print('接続先を登録しました。認証・接続テストはまだ完了していません。')
            return launch_setup('/mcp')
        if name:
            if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}', name): raise ConnectionError('接続名が不正です。')
            current = inventory()
            if any(s.get('name') == name for s in current.get('servers', [])):
                return launch_setup(f'/mcp reconnect {name}')
            print(f'{name} のMCP接続を接続画面で追加してください。APIキー方式には自動で戻しません。')
        return launch_setup()
    except prompts.Cancelled:
        print('中止しました。'); return 130
    except ConnectionError as exc:
        print(str(exc), file=sys.stderr); return 2
