"""Owner-local, read-only dashboard. No model calls, service probes, migration or Git sync."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from functools import wraps
import json
import io
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

from . import config
from .mcp_connections import inventory as mcp_inventory

MAX_FILE = 32 * 1024 * 1024
MAX_RECORDS = 100_000


class DashboardError(ValueError):
    pass


def _read(root: Path, relative: str, limit: int = MAX_FILE) -> bytes | None:
    if root.is_symlink(): raise DashboardError('リンクされたフォルダは表示できません。')
    root = root.resolve()  # Canonicalize OS aliases such as macOS /var -> /private/var.
    path = root / relative
    if '..' in Path(relative).parts or Path(relative).is_absolute(): raise DashboardError('読取先が不正です。')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise DashboardError('リンクされたファイルは表示できません。')
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise DashboardError('ファイルの種類または大きさが表示範囲を超えています。')
        with os.fdopen(fd, 'rb', closefd=False) as stream: data = stream.read(limit + 1)
        if len(data) > limit: raise DashboardError('ファイルが表示上限を超えています。')
        return data
    finally:
        os.close(fd)


def _document(root: Path, relative: str) -> dict | None:
    raw = _read(root, relative)
    if raw is None: return None
    try:
        value = json.loads(raw)
        if not isinstance(value, dict): raise ValueError
        if 'schema_version' in value and (type(value['schema_version']) is not int or value['schema_version'] != 1): raise ValueError
        return value
    except (UnicodeError, ValueError):
        raise DashboardError(f'{relative} の形式を確認できません。ファイルは変更していません。') from None


def _read_only_memory(function):
    @wraps(function)
    def wrapped(home, *args, **kwargs):
        from .storage import file_lock
        home = Path(home)
        if not home.is_dir(): raise DashboardError('記憶フォルダがありません。')
        # Unlike read_home, this never recovers a pending transaction or creates a lock.
        with file_lock(home, create=False):
            if (home / '.watari-pending.json').exists():
                raise DashboardError('記憶の保存処理が中断しています。通常の記憶操作で復旧してください。')
            return function(home, *args, **kwargs)
    return wrapped


@_read_only_memory
def history(home: Path, *, offset: int = 0, limit: int = 50, query: str = '', kind: str = '') -> dict:
    if not 0 <= offset <= 1_000_000 or not 1 <= limit <= 100 or len(query) > 256:
        raise DashboardError('検索範囲が不正です。')
    rows = []
    count = 0
    for genre in ('life', 'learning'):
        raw = _read(home, f'{genre}/log.jsonl')
        if raw is None: continue
        for number, line in enumerate(io.BytesIO(raw), 1):
            if not line.strip(): continue
            count += 1
            if count > MAX_RECORDS or len(line) > 1024 * 1024:
                raise DashboardError('記録が表示上限（合計10万件・1件1MB）を超えています。')
            try:
                row = json.loads(line)
                if not isinstance(row, dict): raise ValueError
                if 'schema_version' in row and (type(row['schema_version']) is not int or row['schema_version'] != 1): raise ValueError
            except (ValueError, UnicodeError):
                raise DashboardError(f'{genre} の記録{number}行目を読み取れません。') from None
            if kind and row.get('kind') != kind: continue
            if query and query.casefold() not in json.dumps(row, ensure_ascii=False).casefold(): continue
            rows.append({**row, 'section': genre, 'line': number})
    rows.sort(key=lambda row: str(row.get('ts', '')), reverse=True)
    end = offset + limit
    return {'rows': rows[offset:end], 'total': len(rows), 'offset': offset,
            'next_offset': end if end < len(rows) else None}


def session_context(value: dict | None) -> dict | None:
    if value is None: return None
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1:
        raise DashboardError('会話環境の形式を確認できません。')
    result = {'version': 1}
    for field in ('model', 'provider', 'thinking'):
        text = value.get(field)
        if text is not None:
            if not isinstance(text, str) or len(text) > 200 or any(ord(c) < 32 for c in text):
                raise DashboardError('会話環境の表示値が不正です。')
            result[field] = text
    tools = value.get('tools', [])
    if not isinstance(tools, list) or len(tools) > 1000 or any(not isinstance(t, str) or len(t) > 200 for t in tools):
        raise DashboardError('道具の一覧が表示上限を超えています。')
    result['tools'] = tools
    return result


@_read_only_memory
def snapshot(home: Path, *, cwd: str, session: dict | None = None) -> dict:
    from .host import runtime_context
    from importlib.metadata import version
    errors = []
    def read(relative):
        try: return _document(home, relative)
        except (OSError, DashboardError):
            errors.append(f'{relative} を表示できません。'); return None
    life, learning = read('life/state.json'), read('learning/state.json')
    try:
        cfg = _document(Path(config._config_dir()), 'config.json') or {}
    except (OSError, DashboardError):
        cfg = {}; errors.append('設定を表示できません。')
    hosts = []
    host_dir = home / 'hosts'
    if host_dir.is_dir() and not host_dir.is_symlink():
        for path in sorted(host_dir.glob('*.json'))[:100]:
            record = read(f'hosts/{path.name}')
            if record:
                hosts.append({k: record[k] for k in ('machine_id', 'hostname', 'computer', 'runtime', 'updated', 'cursors') if k in record})
    legacy = [{k: c.get(k) for k in ('name', 'scope')} for c in cfg.get('connectors', []) if isinstance(c, dict)]
    settings = {k: cfg[k] for k in ('runtime', 'performance') if isinstance(cfg.get(k), str)}
    settings.setdefault('performance', config.DEFAULT_PERFORMANCE_MODE)
    settings['home'] = str(home)
    settings['config_file'] = config._config_file()
    settings['hidden_fields'] = sorted(k for k in cfg if k not in ('runtime', 'performance', 'home'))
    try: package_version = version('watari-cli')
    except Exception: package_version = 'development'
    google = cfg.get('google')
    return {
        'version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(), 'package_version': package_version,
        'computer': runtime_context(), 'memory': {'life': life, 'learning': learning},
        'session': session_context(session), 'settings': settings, 'connections': {'mcp': mcp_inventory(cwd), 'legacy': legacy},
        'sync': {'conversation_credentials_present': bool(isinstance(google, dict) and google.get('refresh_token')),
                 'status': 'not_checked', 'hosts': hosts}, 'errors': errors,
        'capabilities': [
            {'name': '会話と記憶', 'command': 'watari chat', 'detail': '会話から選んだ記憶を保存し、次の会話で参照します。'},
            {'name': '記憶の確認', 'command': '/profile', 'detail': '人物像・進行中事項・関心・学習状況を確認できます。'},
            {'name': '記憶の整理', 'command': '/organize', 'detail': '会話や設定済みの読み取り先から、あとで役に立つことを選びます。'},
            {'name': 'サービスとの接続', 'command': 'watari connect', 'detail': 'MCPの登録・認証・接続確認はPiの接続画面で行います。'},
            {'name': '会話の同期', 'command': 'watari auth', 'detail': 'Google Driveを使う専用の同期機能です。MCPとは別に設定します。'},
            {'name': '性能の選択', 'command': '/performance', 'detail': '返信速度と記憶の詳しさを切り替えます。モデルはPiで選びます。'},
            {'name': 'ダッシュボード', 'command': '/dashboard', 'detail': 'このパソコンの読み取り専用画面を開きます。'},
        ],
    }


def asset(name: str) -> bytes:
    if name not in ('index.html', 'app.js', 'style.css'): raise DashboardError('存在しない画面です。')
    return (Path(__file__).parent / 'dashboard_assets' / name).read_bytes()


class DashboardServer(HTTPServer):
    allow_reuse_address = False
    request_queue_size = 5

    def get_request(self):
        sock, address = super().get_request(); sock.settimeout(5); return sock, address


def make_server(home: Path, *, cwd: str, port: int = 0, session: dict | None = None) -> DashboardServer:
    home = home.absolute()
    if not home.is_dir(): raise DashboardError('記憶フォルダがありません。watari install で設定してください。')
    if (home / '.watari-pending.json').exists():
        raise DashboardError('記憶の保存処理が中断しています。通常の記憶操作で復旧してから開いてください。')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args): pass  # Never log tokens, URLs, search text or memory.

        def reply(self, code: int, data: bytes, content_type='application/json; charset=utf-8'):
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            self.end_headers(); self.wfile.write(data)

        def do_POST(self): self.reply(405, b'{}')
        do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_POST

        def do_GET(self):
            expected = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != expected or self.headers.get('Origin', f'http://{expected}') != f'http://{expected}':
                self.reply(403, b'{}'); return
            parts = urlsplit(self.path)
            if parts.path in ('/', '/app.js', '/style.css'):
                name = parts.path.lstrip('/') or 'index.html'
                mime = {'index.html': 'text/html; charset=utf-8', 'app.js': 'text/javascript; charset=utf-8', 'style.css': 'text/css; charset=utf-8'}[name]
                self.reply(200, asset(name), mime); return
            token = self.headers.get('X-Watari-Token', '')
            if not secrets.compare_digest(token.encode('utf-8'), self.server.access_token.encode('ascii')):
                self.reply(403, b'{}'); return
            try:
                if (home / '.watari-pending.json').exists(): raise DashboardError('記憶の保存処理が中断しています。')
                if parts.path == '/api/snapshot': result = snapshot(home, cwd=cwd, session=session)
                elif parts.path == '/api/history':
                    q = parse_qs(parts.query, max_num_fields=4)
                    result = history(home, offset=int(q.get('offset', ['0'])[0]), query=q.get('q', [''])[0], kind=q.get('kind', [''])[0])
                elif parts.path == '/api/health': result = {'version': 1, 'home': str(home)}
                else: self.reply(404, b'{}'); return
                self.reply(200, json.dumps(result, ensure_ascii=False).encode())
                self.server.last_access = time.monotonic()
            except (ValueError, OSError):
                self.reply(400, json.dumps({'error': '表示できません。記憶・設定の形式、読み取り権限、表示上限（1ファイル32MB）を確認してください。'}, ensure_ascii=False).encode())
    server = DashboardServer(('127.0.0.1', port), Handler)
    server.access_token = secrets.token_urlsafe(32)
    server.last_access = time.monotonic()
    return server


def serve(home: Path, cwd: str, *, ready_file: Path | None = None, session: dict | None = None) -> None:
    with make_server(home, cwd=cwd, session=session) as server:
        url = f'http://127.0.0.1:{server.server_port}/#{server.access_token}'
        if ready_file:
            from .storage import atomic_write_text
            atomic_write_text(ready_file, json.dumps({'url': url, 'pid': os.getpid()}))
        else: print(url, flush=True)
        # One bounded request at a time. Exit after one hour without authenticated reads.
        server.timeout = 2
        while time.monotonic() - server.last_access < 3600:
            server.handle_request()


def open_browser(url: str) -> bool:
    import re
    import shutil
    if not re.fullmatch(r'http://127\.0\.0\.1:[0-9]+/#[A-Za-z0-9_-]+', url):
        raise DashboardError('表示先が不正です。')
    if os.environ.get('WSL_DISTRO_NAME') or os.environ.get('WSL_INTEROP'):
        # Prefer the Windows browser, never launch a WSLg browser as fallback.
        powershell = shutil.which('powershell.exe')
        if not powershell: return False
        try:
            return subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command',
                                   f"Start-Process '{url}'"], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  timeout=5, check=False).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
    try: return bool(webbrowser.open(url))
    except (OSError, webbrowser.Error): return False


def open_dashboard(home: Path, cwd: str, *, browser: bool = True, session: dict | None = None) -> dict:
    """A separate short-lived local process, never a registered system service."""
    import tempfile
    from urllib.request import Request, ProxyHandler, build_opener
    with tempfile.TemporaryDirectory(prefix='watari-dashboard-') as tmp:
        ready = Path(tmp) / 'ready.json'
        proc = subprocess.Popen([sys.executable, '-m', 'watari_cli.dashboard', '--serve', '--home', str(home),
                                 '--cwd', cwd, '--ready-file', str(ready), '--session-context', json.dumps(session_context(session))], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(100):
            if ready.exists(): break
            if proc.poll() is not None: raise DashboardError('ダッシュボードを起動できません。記憶フォルダを確認してください。')
            time.sleep(.05)
        else:
            proc.terminate(); proc.wait(timeout=5); raise DashboardError('ダッシュボードの起動が時間内に完了しませんでした。')
        result = json.loads(ready.read_text())
        parts = urlsplit(result['url'])
        try:
            request = Request(f'http://{parts.netloc}/api/health', headers={'X-Watari-Token': parts.fragment})
            with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
                if json.load(response).get('home') != str(home.absolute()): raise ValueError
        except Exception:
            proc.terminate(); proc.wait(timeout=5); raise DashboardError('ダッシュボードの到達確認に失敗しました。') from None
    result['browser_opened'] = open_browser(result['url']) if browser else False
    result['computer_only'] = True
    result['idle_timeout_seconds'] = 3600
    return result


def cmd_dashboard(args) -> int:
    config.apply(getattr(args, 'home', None))
    home = Path(os.environ.get('WATARI_HOME') or Path.home() / '.local/share/watari/memory').absolute()
    try:
        raw_session = getattr(args, 'session_context', None)
        session = session_context(json.loads(raw_session)) if raw_session else None
        if args.snapshot:
            result = snapshot(home, cwd=os.getcwd(), session=session)
        elif args.serve:
            serve(home, os.getcwd(), session=session); return 0
        else:
            result = open_dashboard(home, os.getcwd(), browser=not args.no_browser, session=session)
        if args.json or args.snapshot: print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"ダッシュボード: {result['url']}\nこのパソコン専用です。1時間使わないと終了します。")
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError) as exc:
        print(f'ダッシュボードを表示できません: {exc}', file=sys.stderr); return 2


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--serve', action='store_true', required=True)
    p.add_argument('--home', required=True)
    p.add_argument('--cwd', required=True)
    p.add_argument('--ready-file')
    p.add_argument('--session-context')
    args = p.parse_args()
    serve(Path(args.home), args.cwd, ready_file=Path(args.ready_file) if args.ready_file else None,
          session=session_context(json.loads(args.session_context)) if args.session_context else None)


if __name__ == '__main__': main()
