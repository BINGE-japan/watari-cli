"""Offline dashboard: real synthetic files, loopback HTTP, no external services."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from watari_cli import dashboard


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / 'memory'
        self.home.mkdir()
        self.env = patch.dict(os.environ, {'HOME': str(self.root), 'PI_CODING_AGENT_DIR': str(self.root / 'pi-agent'), 'WATARI_HOME': str(self.home), 'XDG_CONFIG_HOME': str(self.root / 'config'), 'XDG_STATE_HOME': str(self.root / 'state')})
        self.env.start()
        for genre in ('life', 'learning'):
            (self.home / genre).mkdir()
            (self.home / genre / 'state.json').write_text(json.dumps({'updated': '2026-01-01T00:00:00Z', 'facts': {}}))
            (self.home / genre / 'log.jsonl').write_text('')
        self.row = {'ts': '2026-01-01T00:00:00Z', 'kind': 'fact', 'topic': 'synthetic', 'note': '<img src=x onerror=alert(1)>', 'source': 'watari', 'refs': {'uuid': 'synthetic:1'}}
        (self.home / 'life/log.jsonl').write_text(json.dumps(self.row) + '\n')

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_snapshot_is_read_only_and_does_not_expose_credentials(self):
        from watari_cli import config
        config.save_config(home=str(self.home), performance='balanced', google={'refresh_token': 'synthetic-private-value'}, connectors_auth={'linear': {'api_key': 'another-private-value'}}, connectors=[{'name': 'linear', 'scope': 'cloud', 'read': 'read tasks'}])
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('watari_cli.dashboard.mcp_inventory', return_value={'available': False, 'servers': []}):
            result = dashboard.snapshot(self.home, cwd=str(self.root))
        text = json.dumps(result)
        self.assertNotIn('synthetic-private-value', text)
        self.assertNotIn('another-private-value', text)
        self.assertEqual(result['settings']['performance'], 'balanced')
        self.assertEqual(result['connections']['legacy'][0]['name'], 'linear')
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_history_search_pagination_preserves_closed_topics_and_refs(self):
        rows = [{**self.row, 'topic': f'item-{n}', 'status': 'closed'} for n in range(5)]
        (self.home / 'life/log.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        first = dashboard.history(self.home, limit=2)
        self.assertEqual(first['total'], 5)
        self.assertEqual(first['next_offset'], 2)
        self.assertEqual(len(dashboard.history(self.home, offset=4, limit=2)['rows']), 1)
        found = dashboard.history(self.home, query='item-3')
        self.assertEqual(found['rows'][0]['refs'], {'uuid': 'synthetic:1'})
        self.assertEqual(found['rows'][0]['status'], 'closed')

    def test_links_unknown_versions_and_bad_rows_fail_visibly(self):
        path = self.home / 'life/log.jsonl'
        path.write_text('{broken\n')
        with self.assertRaises(dashboard.DashboardError): dashboard.history(self.home)
        path.write_text(json.dumps({**self.row, 'schema_version': 99}) + '\n')
        with self.assertRaises(dashboard.DashboardError): dashboard.history(self.home)
        path.unlink(); path.symlink_to(self.root / 'outside')
        with self.assertRaises(dashboard.DashboardError): dashboard.history(self.home)

    def test_server_requires_token_exact_host_and_origin_and_has_no_write_routes(self):
        with dashboard.make_server(self.home, cwd=str(self.root)) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            def request(path, headers=None, method='GET'):
                return urlopen(Request(base + path, headers=headers or {}, method=method), timeout=3)
            try:
                with request('/') as response:
                    self.assertIn("default-src 'none'", response.headers['Content-Security-Policy'])
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                    self.assertNotIn(self.row['note'].encode(), response.read())
                with self.assertRaises(HTTPError) as error: request('/api/history')
                self.assertEqual(error.exception.code, 403)
                headers = {'X-Watari-Token': server.access_token}
                with request('/api/history', headers) as response:
                    self.assertEqual(json.load(response)['total'], 1)
                for extra in ({'Host': 'evil.invalid'}, {'Origin': 'https://evil.invalid'}):
                    with self.assertRaises(HTTPError) as error: request('/api/history', {**headers, **extra})
                    self.assertEqual(error.exception.code, 403)
                with self.assertRaises(HTTPError): request('/../../config.json', headers)
                with self.assertRaises(HTTPError) as error: request('/api/history', headers, 'POST')
                self.assertEqual(error.exception.code, 405)
            finally:
                server.shutdown(); thread.join()

    def test_ui_renders_external_text_without_html_execution_or_remote_assets(self):
        source = dashboard.asset('app.js').decode()
        self.assertNotIn('innerHTML', source)
        self.assertIn('textContent', source)
        self.assertNotIn('https://', dashboard.asset('index.html').decode())
        self.assertIn('next_offset', source)

    def test_session_context_only_accepts_display_fields_and_never_credentials(self):
        result = dashboard.session_context({'version': 1, 'model': 'example-model', 'provider': 'example', 'thinking': 'high', 'tools': ['read', 'mcp'], 'api_key': 'synthetic-secret'})
        self.assertEqual(result['model'], 'example-model')
        self.assertNotIn('api_key', result)
        with self.assertRaises(dashboard.DashboardError): dashboard.session_context({'version': 99})
        with self.assertRaises(dashboard.DashboardError): dashboard.session_context({'version': 1, 'tools': ['x'] * 1001})

    def test_history_limits_many_tiny_rows_before_allocating_all_of_them(self):
        (self.home / 'life/log.jsonl').write_text('{}\n' * 4)
        with patch.object(dashboard, 'MAX_RECORDS', 3):
            with self.assertRaises(dashboard.DashboardError): dashboard.history(self.home)

    def test_pending_memory_save_is_never_recovered_by_dashboard(self):
        pending = self.home / '.watari-pending.json'
        pending.write_text('{"version":99}')
        with self.assertRaises(dashboard.DashboardError): dashboard.make_server(self.home, cwd=str(self.root))
        self.assertEqual(pending.read_text(), '{"version":99}')
        with self.assertRaises(dashboard.DashboardError): dashboard.snapshot(self.home, cwd=str(self.root))
        with self.assertRaises(dashboard.DashboardError): dashboard.history(self.home)

    def test_wsl_opens_windows_browser_without_shell_or_wslg(self):
        with patch.dict(os.environ, {'WSL_DISTRO_NAME':'Synthetic'}), patch('shutil.which', return_value='/synthetic/powershell.exe'), patch('subprocess.run') as run, patch('webbrowser.open') as browser:
            run.return_value.returncode = 0
            self.assertTrue(dashboard.open_browser('http://127.0.0.1:1234/#synthetic-token'))
            self.assertEqual(run.call_args.args[0][0], '/synthetic/powershell.exe')
            self.assertFalse(run.call_args.kwargs.get('shell', False))
            browser.assert_not_called()

    def test_startup_health_ignores_http_proxy_configuration(self):
        result = None
        try:
            with patch('urllib.request._opener', None), patch('urllib.request.getproxies', return_value={'http':'http://127.0.0.1:1'}), patch('urllib.request.proxy_bypass', return_value=False):
                result = dashboard.open_dashboard(self.home, str(self.root), browser=False)
            self.assertTrue(result['url'].startswith('http://127.0.0.1:'))
        finally:
            if result:
                import signal
                os.kill(result['pid'], signal.SIGTERM)
                os.waitpid(result['pid'], 0)
