"""MCP-first setup. Pi MCP Adapter owns transports, OAuth, tools and secure token storage.

Network/auth are delegated to the adapter by a bounded, explicitly approved bridge.
Inspection only calls its public config/metadata exports, which do not connect servers.
"""
from __future__ import annotations

import json
import hashlib
from contextlib import contextmanager
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import signal
import threading
import unicodedata
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
                 and not any(c.isspace() or unicodedata.category(c).startswith('C') for c in url) and len(url) <= 2048)
    except ValueError:
        valid = False
    if not valid:
        raise ConnectionError('認証情報・変数・クエリを含まないHTTPSのMCP URLを指定してください。ローカルMCPは接続画面で設定できます。')
    return url


@contextmanager
def _locked_shared_config():
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
            raise ConnectionError('既存の接続設定を安全に読み取れません。watari connect --advanced で編集してください。') from None
        yield path, value


def register_remote(name: str, url: str, *, auth: str = 'auto') -> None:
    if auth not in ('auto', 'oauth', 'bearer', 'none'):
        raise ConnectionError('認証方式が不正です。')
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,62}', name):
        raise ConnectionError('接続名は小文字の英字で始まる英数字とハイフンで指定してください。')
    validate_url(url)
    with _locked_shared_config() as (path, value):
        servers = value.setdefault('mcpServers', {})
        if name in servers:
            if isinstance(servers[name], dict) and servers[name].get('url') == url:
                return
            raise ConnectionError('同じ名前の接続が存在します。別名を指定するか接続画面で確認してください。')
        servers[name] = {'url': url, 'lifecycle': 'lazy', 'approveTools': True}
        if auth != 'auto': servers[name]['auth'] = False if auth == 'none' else auth
        if auth == 'bearer': servers[name]['bearerTokenStore'] = True
        # Default server-driven model calls off; do not change an existing explicit policy.
        settings = value.setdefault('settings', {})
        if not isinstance(settings, dict): raise ConnectionError('接続設定の形式が不正です。')
        settings.setdefault('sampling', False)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        storage.atomic_write_text(str(path), storage.json_text(value))


def switch_to_token(server: dict) -> None:
    """Explicit user-approved edit of a simple shared entry, never credentials."""
    with _locked_shared_config() as (path, value):
        current = _checked_inventory()
        effective = next((s for s in current['servers'] if s['name'] == server['name']), None)
        if not server.get('connection_binding') or not effective or effective.get('connection_binding') != server['connection_binding']:
            raise ConnectionError('確認後に設定が変わりました。もう一度 watari connect を開いてください。')
        definition = value.get('mcpServers', {}).get(server['name'])
        allowed = {'url','auth','bearerTokenStore','lifecycle','approveTools','protocolVersion'}
        if not isinstance(definition, dict) or set(definition) - allowed:
            raise ConnectionError('詳細な認証設定または別の保存先を使用しています。watari connect --advanced で変更してください。')
        fingerprint = hashlib.sha256(json.dumps(sorted(definition.items()), ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        if fingerprint != server.get('definition_fingerprint'):
            raise ConnectionError('別の設定が優先されているか、設定が変わっています。watari connect --advanced で確認してください。')
        validate_url(definition.get('url', ''))
        definition['auth'] = 'bearer'
        definition['bearerTokenStore'] = True
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
        return {'available': True, 'servers': [], 'error': 'MCP設定を確認できません。watari connect --advanced で確認してください。'}


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


def _display(value: object) -> str:
    # Config/remote names are data, not terminal control sequences.
    return ''.join(c for c in str(value) if not unicodedata.category(c).startswith('C'))[:300]


def run_operation(server: dict, action: str) -> dict:
    """Only the selected, confirmed definition. Secrets never transit Python."""
    root, node = adapter_root(), shutil.which('node')
    binding = server.get('connection_binding')
    if not root or not node or not isinstance(binding, str) or not re.fullmatch('[a-f0-9]{64}', binding):
        raise ConnectionError('接続設定を確認できません。watari connect --advanced で確認してください。')
    if action not in ('check', 'auth'): raise ConnectionError('操作が不正です。')
    helper = Path(__file__).parent / 'pi/mcp-management.mjs'
    argv = [node, str(helper), str(root), action, server['name'], binding, os.getcwd()]
    # The helper inherits only the terminal input. Its own masked prompt reads
    # secrets; stdout is a bounded allowlist of progress events and safe results.
    terminal = None
    if os.name == 'posix' and sys.stdin.isatty():
        import termios
        fd = sys.stdin.fileno()
        terminal = (fd, termios.tcgetattr(fd))
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, start_new_session=(os.name == 'posix'))

    def terminate(force=False):
        if os.name != 'posix' and process.poll() is not None: return
        try:
            if os.name == 'posix': os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
            elif force: process.kill()
            else: process.terminate()
        except ProcessLookupError: pass

    timer = threading.Timer(190 if action == 'auth' else 40, lambda: terminate(True))
    timer.daemon = True; timer.start()
    result = None
    statuses = {'connected','needs-auth','changed','disabled','missing','invalid','cancelled','error',
                'credential-store-unavailable','cleanup-failed','config-error','unsupported-version',
                'unsupported-auth','advanced-auth','tty-required','oauth-client-required','forbidden',
                'network-error','server-error','timeout','adapter-error'}
    try:
        size = 0
        while line := process.stdout.readline(16385):
            size += len(line)
            if len(line) > 16384 or size > 65536: raise ValueError
            event = json.loads(line)
            if not isinstance(event, dict): raise ValueError
            if event.get('event') == 'authorization' and action == 'auth':
                url = event.get('url', '')
                parsed = urlsplit(url)
                if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                        or any(ord(c) < 33 or 127 <= ord(c) <= 159 for c in url)): raise ValueError
                print(f'ブラウザで認証してください。開かない場合はこのURLを開いてください。\n{url}', flush=True)
            elif event.get('event') == 'input' and action == 'auth':
                if event.get('kind') == 'token':
                    print('アクセストークンを貼り付けてEnter（入力は非表示）:', flush=True)
                elif event.get('kind') == 'callback':
                    print('認証完了を待っています。自動で戻れない場合はブラウザの転送先URLを貼り付けてEnter（非表示）:', flush=True)
                else: raise ValueError
            elif type(event.get('version')) is int and event['version'] == 1 and event.get('status') in statuses:
                if result is not None: raise ValueError
                result = {'version':1, 'status':event['status']}
                if event['status'] == 'connected':
                    count = event.get('tool_count')
                    if type(count) is not int or not 0 <= count <= 100000: raise ValueError
                    result['tool_count'] = count
            else: raise ValueError
        if process.wait(timeout=5) or result is None: raise ValueError
        return result
    except (ValueError, OSError, subprocess.TimeoutExpired):
        raise ConnectionError('接続処理を完了できませんでした。再度実行するか watari connect --advanced で確認してください。') from None
    finally:
        timer.cancel(); terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: terminate(True); process.wait()
        process.stdout.close()
        if terminal:
            try: termios.tcsetattr(terminal[0], termios.TCSANOW, terminal[1])
            except OSError: pass


def _checked_inventory() -> dict:
    value = inventory()
    if not value.get('available'):
        raise ConnectionError(f'MCP接続にはPi MCP Adapterが必要です。\n  {ADAPTER_INSTALL}\n導入後に watari connect をもう一度実行してください。')
    if value.get('error'): raise ConnectionError(value['error'])
    return value


def _manage_server(server: dict, *, prefer_auth: bool = False) -> int:
    from . import prompts
    name = server['name']
    print(f"\n{_display(name)} — {_display(server.get('endpoint') or server.get('transport', ''))}")
    if server.get('status') == 'disabled':
        print('この接続は無効です。有効化は watari connect --advanced で行ってください。')
        return 2
    options = [('接続を確認', 'check')]
    if server.get('transport') == 'http' and server.get('authentication') != 'none': options.append(('認証して接続を確認', 'auth'))
    if server.get('transport') == 'http' and server.get('authentication') != 'bearer':
        options.append(('アクセストークン方式に切り替える', 'token'))
    options += [('詳細設定（Pi）', 'advanced'), ('終了', None)]
    if server.get('oauth_setup_required') and server.get('authentication') in ('auto','oauth'):
        print('このサービスのブラウザ認証には接続アプリの事前登録が必要です。未登録の場合はアクセストークン方式を選んでください。')
        default = next((i for i, (_, mode) in enumerate(options) if mode == 'token'), 0)
    else:
        default = next((i for i, (_, mode) in enumerate(options) if prefer_auth and mode == 'auth'), 0)
    action = prompts.select('操作を選んでください', options, default=default)
    if action is None: return 0
    if action == 'advanced': return launch_setup('/mcp')
    if action == 'token':
        print(f'この接続の認証方式をアクセストークン方式へ変更します。保存先: {shared_config_path()}')
        print('保存済みの認証情報や、ほかの接続は削除しません。')
        if not prompts.confirm('この認証方式へ変更しますか？', default=False): return 0
        switch_to_token(server)
        fresh = next((s for s in _checked_inventory()['servers'] if s['name'] == name), None)
        if not fresh or fresh.get('authentication') != 'bearer':
            raise ConnectionError('変更後の設定を確認できません。watari connect --advanced で確認してください。')
        return _manage_server(fresh, prefer_auth=True)
    if server.get('transport') in ('stdio','socket'):
        print('設定済みのローカルプログラムを実行、またはローカル接続を開始します。')
    else:
        print('このサービスと通信します。設定によっては認証用のローカルプログラムも実行されます。')
    if action == 'auth':
        print('認証情報はPi MCP Adapterの既存の保管先へ保存します。')
        if server.get('authentication') == 'bearer' and server.get('token_help_url') == 'https://github.com/settings/personal-access-tokens/new':
            print('GitHubのFine-grained personal access tokenを作成し、対象リポジトリと必要最小限の権限だけを選んでください。')
            print(server['token_help_url'])
            print('トークンはこの端末の非表示入力へ貼り付けてください。チャットには貼らないでください。')
    print('ツールの実行やAIへの送信は行いません。中止はCtrl+Cです。')
    if not prompts.confirm('この接続先で実行しますか？', default=False): return 0
    print('認証・接続を確認しています。' if action == 'auth' else '接続を確認しています。', flush=True)
    result = run_operation(server, action)
    status = result['status']
    if status == 'connected':
        print(f"接続確認に成功しました。利用可能なツール: {result['tool_count']}件。")
        print('watari chat で利用できます。既に開いている会話には再起動が必要な場合があります。')
        return 0
    messages = {
        'oauth-client-required':'このサービスはOAuth接続アプリの事前登録が必要です。認証方式をアクセストークンへ切り替えるか、詳細設定で登録済みアプリを指定してください。',
        'forbidden':'サービスがアクセスを拒否しました（HTTP 403）。トークンの権限・対象リポジトリ・組織側の利用許可を確認してください。',
        'network-error':'通信先へ接続できません。インターネット接続・DNS・プロキシ設定を確認してください。',
        'server-error':'サービス側で一時エラーまたは利用制限が発生しています。時間を置いて再試行してください。',
        'timeout':'接続処理が時間内に完了しませんでした。通信状態を確認して再試行してください。',
        'adapter-error':'接続用プログラムの読込または初期設定に失敗しました。Pi MCP Adapterの導入状態を確認してください。',
        'needs-auth':'認証が必要です。もう一度 watari connect を開き「認証して接続を確認」を選んでください。',
        'changed':'確認後に設定が変わりました。もう一度 watari connect を開いて接続先を確認してください。',
        'credential-store-unavailable':'認証情報の保管先を利用できません。OSのキーチェーン設定を確認するか watari connect --advanced を開いてください。',
        'unsupported-version':'このAdapter版でのワタリ接続操作は未検証です。watari connect --advanced を利用してください。',
        'advanced-auth':'既存の認証設定が優先されます。watari connect --advanced で設定を確認してください。',
        'unsupported-auth':'この接続の認証はここでは設定できません。watari connect --advanced を利用してください。',
        'cancelled':'中止しました。認証情報を既に保存した場合はそのまま保持します。',
        'tty-required':'認証はお使いのターミナルで watari connect を直接実行してください。',
    }
    print(messages.get(status, '接続確認が完了しませんでした。保存済みの設定・認証情報は保持します。再試行するか watari connect --advanced で確認してください。'))
    return 1


def _add_remote(current: dict, name: str | None, url: str | None) -> int:
    from . import prompts
    presets = current.get('presets', [])
    preset = next((p for p in presets if p.get('id') == name), None) if not url else None
    if not name and not url:
        preset = prompts.select('追加するサービス', [(_display(p['name']), p) for p in presets] + [('URLを入力', {}), ('終了', None)])
        if preset is None: return 0
    if preset:
        name = name or preset['id']; url = preset['url']
    url = url or prompts.text('サービスが案内するHTTPSのMCP URL')
    validate_url(url)
    name = name or prompts.text('接続名（例: team-docs）')
    if any(s.get('name') == name for s in current.get('servers', [])):
        raise ConnectionError('同じ名前のMCP接続が既に設定されています。一覧から選ぶか別の接続名にしてください。')
    preset = preset or next((p for p in presets if p.get('url', '').rstrip('/') == url.rstrip('/')), None)
    if preset and preset.get('oauth_setup_required'):
        print('このサービスのブラウザ認証にはアプリの事前登録が必要です。ここではアクセストークンで接続します。')
        modes = [('アクセストークンを入力','bearer')]
    else:
        modes = [('ブラウザでログイン（OAuth）','oauth'),('アクセストークンを入力','bearer'),('認証不要','none')]
    default = next((i for i, (_, mode) in enumerate(modes) if preset and mode == preset.get('auth')), 0)
    auth = prompts.select('サービス指定の認証方式', modes, default=default)
    print(f'MCP接続先: {url}\n接続名: {_display(name)}\n保存先: {shared_config_path()}')
    print('信頼するサービスだけを登録してください。')
    if not prompts.confirm('この接続を登録しますか？', default=False): return 0
    register_remote(name, url, auth=auth)
    print('接続先を登録しました。認証・接続確認はまだ完了していません。')
    fresh = _checked_inventory()
    server = next((s for s in fresh['servers'] if s['name'] == name), None)
    if not server: raise ConnectionError('登録後の設定を確認できません。watari connect --advanced を開いてください。')
    return _manage_server(server, prefer_auth=True)


def connect(args) -> int:
    from . import prompts
    try:
        if getattr(args, 'list', False):
            value = inventory()
            print(json.dumps(value, ensure_ascii=False, indent=2))
            return 2 if value.get('error') or not value.get('available') else 0
        if getattr(args, 'advanced', False): return launch_setup()
        name, url = args.service, getattr(args, 'url', None)
        if name and name.startswith('https://'): url, name = name, None
        current = _checked_inventory()
        if url: return _add_remote(current, name, url)
        if name:
            if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}', name): raise ConnectionError('接続名が不正です。')
            server = next((s for s in current['servers'] if s['name'] == name), None)
            return _manage_server(server) if server else _add_remote(current, name, None)
        print('登録済みの接続（この画面では通信しません。接続・認証は未確認です）')
        for s in current['servers']:
            print(f"  {_display(s['name'])} — {_display(s.get('endpoint') or s.get('transport',''))}" + ('（無効）' if s.get('status') == 'disabled' else ''))
        options = [(_display(s['name']), s) for s in current['servers']]
        options += [('接続を追加', 'add'), ('詳細設定（Pi）', 'advanced'), ('終了', None)]
        choice = prompts.select('ワタリのサービス接続', options)
        if choice is None: return 0
        if choice == 'advanced': return launch_setup()
        if choice == 'add': return _add_remote(current, None, None)
        return _manage_server(choice)
    except (prompts.Cancelled, KeyboardInterrupt):
        print('中止しました。'); return 130
    except (ConnectionError, OSError) as exc:
        # OSError can contain arbitrary command/path details; only our curated errors are shown.
        print(str(exc) if isinstance(exc, ConnectionError) else '接続操作を開始できませんでした。Node/Piの導入状態を確認してください。', file=sys.stderr)
        return 2
