"""Watari-owned management flow; no real service, credentials or Pi session."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from watari_cli import mcp_connections as mcp, prompts
from watari_cli.cli import _build_parser


class ConnectManagementTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'HOME': str(self.root), 'WATARI_HOME': str(self.root/'memory'), 'XDG_CONFIG_HOME': str(self.root/'config'), 'XDG_STATE_HOME': str(self.root/'state'), 'PI_CODING_AGENT_DIR': str(self.root/'pi')})
        self.env.start()
        self.server = {'name':'example','endpoint':'https://mcp.example.com','transport':'http','status':'configured','connection_binding':'a'*64}
        self.inventory = {'available':True,'version':1,'servers':[self.server], 'presets':[]}

    def tearDown(self):
        self.env.stop(); self.tmp.cleanup()

    def run_connect(self, argv):
        args = _build_parser().parse_args(['connect', *argv])
        return mcp.connect(args)

    def test_default_opens_watari_list_without_starting_pi_or_connecting(self):
        with patch.object(mcp,'inventory',return_value=self.inventory), patch.object(prompts,'select',return_value=None) as select, patch.object(mcp,'launch_setup') as pi, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.run_connect([]),0)
        pi.assert_not_called()
        self.assertIn('ワタリ',select.call_args.args[0])
        self.assertIn('example',out.getvalue())
        self.assertIn('未確認',out.getvalue())

    def test_existing_connection_is_checked_only_after_human_confirmation(self):
        with patch.object(mcp,'inventory',return_value=self.inventory), patch.object(prompts,'select',return_value='check'), patch.object(prompts,'confirm',return_value=True), patch.object(mcp,'run_operation',return_value={'version':1,'status':'connected','tool_count':4}) as operation, patch.object(mcp,'launch_setup') as pi, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.run_connect(['example']),0)
        operation.assert_called_once_with(self.server,'check')
        pi.assert_not_called()
        self.assertIn('接続確認に成功',out.getvalue())

    def test_cancelled_confirmation_never_contacts_service(self):
        with patch.object(mcp,'inventory',return_value=self.inventory), patch.object(prompts,'select',return_value='auth'), patch.object(prompts,'confirm',return_value=False), patch.object(mcp,'run_operation') as operation:
            self.assertEqual(self.run_connect(['example']),0)
        operation.assert_not_called()

    def test_authentication_returns_to_watari_with_actual_check_result(self):
        with patch.object(mcp,'inventory',return_value=self.inventory), patch.object(prompts,'select',return_value='auth'), patch.object(prompts,'confirm',return_value=True), patch.object(mcp,'run_operation',return_value={'version':1,'status':'connected','tool_count':2}) as operation, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.run_connect(['example']),0)
        operation.assert_called_once_with(self.server,'auth')

    def test_needs_auth_is_not_reported_as_connected(self):
        with patch.object(mcp,'inventory',return_value=self.inventory), patch.object(prompts,'select',return_value='check'), patch.object(prompts,'confirm',return_value=True), patch.object(mcp,'run_operation',return_value={'version':1,'status':'needs-auth'}) as operation, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.run_connect(['example']),1)
        self.assertNotIn('成功',out.getvalue())
        self.assertIn('認証',out.getvalue())

    def test_new_url_registration_and_authentication_do_not_handoff_to_pi(self):
        inv = {'available':True,'version':1,'servers':[], 'presets':[]}
        with patch.object(mcp,'inventory',side_effect=[inv,self.inventory]), patch.object(mcp,'adapter_root',return_value=self.root), patch.object(prompts,'select',side_effect=['oauth','auth']), patch.object(prompts,'confirm',return_value=True), patch.object(mcp,'register_remote') as save, patch.object(mcp,'run_operation',return_value={'version':1,'status':'connected','tool_count':1}), patch.object(mcp,'launch_setup') as pi, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.run_connect(['example','--url','https://mcp.example.com/mcp']),0)
        save.assert_called_once_with('example','https://mcp.example.com/mcp',auth='oauth')
        pi.assert_not_called()

    def test_advanced_settings_remain_an_explicit_escape_hatch(self):
        with patch.object(mcp,'launch_setup',return_value=0) as pi:
            self.assertEqual(self.run_connect(['--advanced']),0)
        pi.assert_called_once()

    def test_bearer_registration_stores_only_reference_not_token(self):
        with patch.object(mcp,'shared_config_path',return_value=self.root/'mcp.json'):
            mcp.register_remote('example','https://mcp.example.com/mcp',auth='bearer')
        value=json.loads((self.root/'mcp.json').read_text())['mcpServers']['example']
        self.assertEqual(value['auth'],'bearer')
        self.assertIs(value['bearerTokenStore'],True)
        self.assertNotIn('bearerToken',value)

    def test_no_authentication_uses_adapters_boolean_false_not_unknown_enum(self):
        with patch.object(mcp, 'shared_config_path', return_value=self.root/'mcp.json'):
            mcp.register_remote('example','https://mcp.example.com/mcp',auth='none')
        self.assertIs(json.loads((self.root/'mcp.json').read_text())['mcpServers']['example']['auth'],False)

    def test_new_flags_reject_ambiguous_modes(self):
        for argv in (['--advanced','--list'], ['--advanced','--legacy'], ['obsidian','--advanced'], ['--list','--url','https://mcp.example.com/mcp'], ['example','--list']):
            with self.subTest(argv=argv), patch('sys.stdin.isatty',return_value=True), patch.object(mcp,'connect') as connect, contextlib.redirect_stderr(io.StringIO()):
                args=_build_parser().parse_args(['connect',*argv])
                self.assertEqual(args.func(args),2)
                connect.assert_not_called()

    def fake_adapter(self, auth='oauth'):
        root=self.root/'adapter'; (root/'dist').mkdir(parents=True)
        (root/'package.json').write_text('{"type":"module","version":"2.37.0"}')
        config={'mcpServers':{'example':{'url':'https://mcp.example.com/mcp','auth':auth,'bearerTokenStore':True}}}
        modules={
            'config.js':f'export const loadMcpConfig=()=>({json.dumps(config)}); export const getServerProvenance=()=>new Map(); export const getMcpStandardConfigSummary=()=>({{sources:[]}});',
            'metadata-cache.js':'export const computeServerHash=()=>"synthetic"; export const loadMetadataCache=()=>({}); export const isServerCacheValid=()=>false;',
            'server-manager.js':'''export class McpServerManager {
                setAuthStorageOptions(){} setOAuthRuntime(){} setRuntimeSignal(){} setDefaultRequestTimeoutMs(){} setTraceConfig(){}
                async connect(){return {status:'connected',tools:[{name:'lookup'}]};} async closeAll(){}
            }''',
            'mcp-auth-flow.js':'''export const createOAuthRuntime=()=>({}); export const supportsOAuth=()=>true;
                export const authenticate=async()=> 'authenticated'; export const shutdownOAuth=async()=>{};''',
            'mcp-auth.js':'export const getAuthStorageOptions=()=>({});',
            'utils.js':'export const resolveServerUrl=definition=>definition.url;',
            'mcp-bearer-store.js':'''export const saveBearerTokenForUrl=(name,token,url)=>{
                if(name!=='example'||token!=='synthetic-hidden-token'||url!=='https://mcp.example.com/mcp')throw new Error('wrong synthetic token');
            };''',
        }
        for name,content in modules.items(): (root/'dist'/name).write_text(content)
        return root

    def test_bridge_checks_selected_server_and_refuses_unknown_adapter_versions(self):
        root=self.fake_adapter()
        with patch.object(mcp,'adapter_root',return_value=root):
            server=mcp.inventory()['servers'][0]
            self.assertEqual(mcp.run_operation(server,'check'),{'version':1,'status':'connected','tool_count':1})
            (root/'package.json').write_text('{"type":"module","version":"99.0.0"}')
            self.assertEqual(mcp.run_operation(server,'check')['status'],'unsupported-version')

    def test_bridge_rejects_authentication_without_terminal(self):
        import subprocess, shutil
        root=self.fake_adapter()
        with patch.object(mcp,'adapter_root',return_value=root): server=mcp.inventory()['servers'][0]
        helper=Path(mcp.__file__).parent/'pi/mcp-management.mjs'
        result=subprocess.run([shutil.which('node'),str(helper),str(root),'auth','example',server['connection_binding'],os.getcwd()],input='',capture_output=True,text=True,timeout=10)
        self.assertEqual(json.loads(result.stdout)['status'],'tty-required')

    def test_bearer_secret_is_not_echoed_or_returned_and_terminal_is_restored(self):
        import pty, termios, subprocess, shutil, select
        root=self.fake_adapter(auth='bearer')
        with patch.object(mcp,'adapter_root',return_value=root): server=mcp.inventory()['servers'][0]
        helper=Path(mcp.__file__).parent/'pi/mcp-management.mjs'
        master,slave=pty.openpty(); before=termios.tcgetattr(slave)
        process=subprocess.Popen([shutil.which('node'),str(helper),str(root),'auth','example',server['connection_binding'],os.getcwd()],stdin=slave,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            self.assertTrue(select.select([process.stdout],[],[],5)[0])
            event=json.loads(process.stdout.readline()); self.assertEqual(event,{'event':'input','kind':'token'})
            # Event is emitted immediately before readline switches to hidden input.
            import time
            deadline=time.monotonic()+5
            while termios.tcgetattr(slave)[3] & termios.ECHO:
                if time.monotonic()>deadline: self.fail('secret input did not disable echo')
                time.sleep(.01)
            os.write(master,b'synthetic-hidden-token\n')
            stdout,stderr=process.communicate(timeout=10)
            self.assertEqual(json.loads(stdout)['status'],'connected')
            self.assertNotIn(b'synthetic-hidden-token',stdout+stderr)
            self.assertEqual(termios.tcgetattr(slave),before)
            echoed=os.read(master,4096) if select.select([master],[],[],0)[0] else b''
            self.assertNotIn(b'synthetic-hidden-token',echoed)
        finally:
            if process.poll() is None: process.kill(); process.wait()
            process.stdout.close(); process.stderr.close(); os.close(master); os.close(slave)

    def test_new_url_rejects_terminal_control_and_bidi_format_characters(self):
        for character in ('\u009b','\u202e','\u2066'):
            with self.subTest(character=repr(character)), self.assertRaises(mcp.ConnectionError):
                mcp.validate_url('https://mcp.example.com/'+character+'mcp')

    def test_parent_restores_terminal_after_bridge_crashes_during_secret_input(self):
        import pty, termios, subprocess, threading, time, signal
        from unittest.mock import MagicMock
        root=self.fake_adapter(auth='bearer')
        with patch.object(mcp,'adapter_root',return_value=root): server=mcp.inventory()['servers'][0]
        master,slave=pty.openpty(); before=termios.tcgetattr(slave)
        real_popen=subprocess.Popen; children=[]; workers=[]
        terminal=MagicMock(); terminal.isatty.return_value=True; terminal.fileno.return_value=slave
        def start(argv,**kwargs):
            kwargs['stdin']=slave
            process=real_popen(argv,**kwargs); children.append(process)
            def crash():
                deadline=time.monotonic()+5
                while termios.tcgetattr(slave)[3] & termios.ECHO and time.monotonic()<deadline:
                    time.sleep(.01)
                if process.poll() is None: os.kill(process.pid,signal.SIGKILL)
            thread=threading.Thread(target=crash); thread.start(); workers.append(thread)
            return process
        try:
            with patch.object(mcp,'adapter_root',return_value=root), patch.object(mcp.subprocess,'Popen',side_effect=start), patch.object(mcp.sys,'stdin',terminal), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(mcp.ConnectionError): mcp.run_operation(server,'auth')
            for thread in workers: thread.join(timeout=6)
            self.assertEqual(termios.tcgetattr(slave),before)
        finally:
            for process in children:
                if process.poll() is None: process.kill(); process.wait()
            for thread in workers: thread.join(timeout=6)
            termios.tcsetattr(slave,termios.TCSANOW,before);os.close(master);os.close(slave)
