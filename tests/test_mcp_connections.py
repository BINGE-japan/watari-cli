"""MCP-first connect delegates protocol/auth to the installed Pi adapter."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from watari_cli import mcp_connections as mcp
from watari_cli.cli import _build_parser


class McpConnectionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'HOME': str(self.root), 'XDG_CONFIG_HOME': str(self.root / 'config'), 'PI_CODING_AGENT_DIR': str(self.root / 'pi'), 'XDG_STATE_HOME': str(self.root / 'state'), 'WATARI_HOME': str(self.root / 'memory')})
        self.env.start()

    def tearDown(self):
        self.env.stop(); self.tmp.cleanup()

    def test_connect_defaults_to_mcp_and_direct_services_require_explicit_legacy(self):
        with patch('watari_cli.mcp_connections.connect', return_value=0) as connect, patch('sys.stdin.isatty', return_value=True):
            args = _build_parser().parse_args(['connect', 'notion'])
            self.assertEqual(args.func(args), 0)
            connect.assert_called_once()
        with patch('watari_cli.cli._connect_wizard', return_value=0) as legacy, patch('sys.stdin.isatty', return_value=True):
            args = _build_parser().parse_args(['connect', 'linear', '--legacy'])
            self.assertEqual(args.func(args), 0)
            legacy.assert_called_once_with('linear')

    def test_local_sources_remain_local_without_mcp(self):
        with patch('watari_cli.cli._connect_wizard', return_value=0) as local, patch('sys.stdin.isatty', return_value=True):
            args = _build_parser().parse_args(['connect', 'obsidian'])
            self.assertEqual(args.func(args), 0)
            local.assert_called_once_with('obsidian')

    def test_mcp_setup_uses_no_model_or_legacy_auth_and_loads_installed_adapter(self):
        adapter = self.root / 'adapter'; adapter.mkdir(); (adapter / 'index.ts').write_text('')
        with patch.object(mcp, 'adapter_root', return_value=adapter), patch('watari_cli.cli._runtime_base', return_value=['pi']), patch('subprocess.run') as run:
            run.return_value.returncode = 0
            self.assertEqual(mcp.launch_setup(), 0)
            argv = run.call_args.args[0]
            self.assertIn('--no-extensions', argv)
            self.assertIn(str(adapter / 'index.ts'), argv)
            self.assertIn('--no-session', argv)
            self.assertEqual(run.call_args.kwargs['env']['WATARI_CONNECT_COMMAND'], '/mcp setup')
            self.assertNotIn('--print', argv)

    def test_missing_adapter_does_not_install_or_modify_configuration(self):
        with patch.object(mcp, 'adapter_root', return_value=None), patch('subprocess.run') as run, contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(mcp.launch_setup(), 2)
        run.assert_not_called()
        self.assertIn('pi install npm:pi-mcp-adapter', err.getvalue())
        self.assertFalse((self.root / 'pi').exists())

    def test_registration_preserves_other_servers_and_rejects_collisions_and_secret_urls(self):
        # Only a new explicit registration; no reading/migrating credentials.
        with patch.object(mcp, 'shared_config_path', return_value=self.root / 'mcp.json'):
            mcp.register_remote('example', 'https://mcp.example.com/mcp')
            value = json.loads((self.root / 'mcp.json').read_text())
            self.assertTrue(value['mcpServers']['example']['approveTools'])
            with self.assertRaises(mcp.ConnectionError): mcp.register_remote('example', 'https://other.example.com/mcp')
            mcp.register_remote('other', 'https://other.example.com/mcp')
            self.assertEqual(len(json.loads((self.root / 'mcp.json').read_text())['mcpServers']), 2)
            for url in ('https://user:pass@example.com/mcp', 'https://example.com/mcp?token=secret', 'file:///tmp/a', 'http://example.com/mcp', 'https://example.com/${TOKEN}'):
                with self.subTest(url=url), self.assertRaises(mcp.ConnectionError): mcp.register_remote('bad', url)

    def test_saved_definition_is_not_reported_as_authenticated(self):
        with patch.object(mcp, 'inventory', return_value={'available': True, 'servers': [{'name': 'example', 'status': 'configured'}]}), contextlib.redirect_stdout(io.StringIO()) as out:
            args = _build_parser().parse_args(['connect', '--list'])
            self.assertEqual(args.func(args), 0)
        self.assertIn('configured', out.getvalue())
        self.assertNotIn('接続済み', out.getvalue())

    def test_missing_mcp_settings_parent_is_created_and_file_is_private(self):
        path = self.root / 'new' / 'mcp.json'
        with patch.object(mcp, 'shared_config_path', return_value=path):
            mcp.register_remote('example', 'https://mcp.example.com/mcp')
        if os.name == 'posix': self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_linked_or_unknown_config_is_not_changed(self):
        target = self.root / 'elsewhere.json'; target.write_text('{}')
        path = self.root / 'mcp.json'; path.symlink_to(target)
        with patch.object(mcp, 'shared_config_path', return_value=path):
            with self.assertRaises(mcp.ConnectionError): mcp.register_remote('example', 'https://mcp.example.com/mcp')
            self.assertEqual(target.read_text(), '{}')
            path.unlink(); path.write_text('{"schema_version":99}')
            with self.assertRaises(mcp.ConnectionError): mcp.register_remote('example', 'https://mcp.example.com/mcp')
            self.assertEqual(json.loads(path.read_text()), {'schema_version': 99})

    def test_conflicting_connection_modes_do_not_silently_choose_a_writer(self):
        for argv in (['connect', '--legacy', '--url', 'https://mcp.example.com/mcp'], ['connect', 'obsidian', '--url', 'https://mcp.example.com/mcp'], ['connect', '--legacy', '--list']):
            with self.subTest(argv=argv), patch('sys.stdin.isatty', return_value=True), patch('watari_cli.cli._connect_wizard') as legacy, patch('watari_cli.mcp_connections.connect') as remote, contextlib.redirect_stderr(io.StringIO()):
                args = _build_parser().parse_args(argv)
                self.assertEqual(args.func(args), 2)
                legacy.assert_not_called(); remote.assert_not_called()

    def test_inventory_projects_adapter_metadata_without_headers_environment_or_arguments(self):
        root = self.root / 'adapter'; (root / 'dist').mkdir(parents=True)
        (root / 'package.json').write_text('{"type":"module"}')
        (root / 'dist/config.js').write_text('''
export const loadMcpConfig = () => ({mcpServers: {example:{url:'https://user:secret@example.com/private?api_key=secret', headers:{Authorization:'secret-header'},env:{TOKEN:'secret-env'},args:['secret-arg']}}});
export const getServerProvenance = () => new Map([['example',{path:'/synthetic/override.json'}]]);
export const getMcpStandardConfigSummary = () => ({sources:[{exists:true,path:'/synthetic/mcp.json'}]});
''')
        (root / 'dist/metadata-cache.js').write_text('''
export const loadMetadataCache = () => ({servers:{example:{tools:[{name:'search',inputSchema:{secret:'secret-schema'}}]}}});
export const isServerCacheValid = () => true;
''')
        with patch.object(mcp, 'adapter_root', return_value=root): result = mcp.inventory(str(self.root))
        self.assertEqual(result['servers'][0]['endpoint'], 'https://example.com')
        self.assertEqual(result['servers'][0]['tools'], [{'name': 'search'}])
        self.assertEqual(result['config_files'], ['/synthetic/mcp.json'])
        self.assertNotIn('secret', json.dumps(result))

    def test_url_registration_cannot_shadow_an_effective_connection(self):
        args = _build_parser().parse_args(['connect', 'example', '--url', 'https://mcp.example.com/mcp'])
        with patch.object(mcp, 'adapter_root', return_value=self.root), patch.object(mcp, 'inventory', return_value={'available':True,'servers':[{'name':'example'}]}), patch.object(mcp,'register_remote') as save, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(mcp.connect(args), 2)
            save.assert_not_called()
