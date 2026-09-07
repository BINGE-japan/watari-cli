"""Review-only desired-behavior probes: synthetic files, fake transports, no live reads."""

import builtins

import contextlib

import json

import os

from pathlib import Path

import subprocess

import threading

from datetime import datetime, timedelta, timezone

from unittest.mock import patch

import pytest

from watari_cli import config, host, relay, cloud, linear, google_connectors, git_sync, slack

from watari_cli.engine import ingest, regen_state, watari_lib as wl, extract

@pytest.fixture
def isolated(tmp_path, monkeypatch):
    home = tmp_path / 'memory'
    for genre in ('life','learning'):
        (home / genre).mkdir(parents=True)
        (home / genre / 'log.jsonl').write_text('')
    monkeypatch.setattr(wl, 'MEM', str(home))
    monkeypatch.setattr(ingest, 'MEM', str(home))
    monkeypatch.setattr(host, 'machine_id', lambda: 'synthetic-review')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    return home

def row(uuid='review', **kwargs):
    return dict(ts='2026-09-01T00:00:00.000Z',source='watari',kind='thread',
                topic='Synthetic task',summary='Synthetic evidence',note='Open',
                refs={'uuid':uuid}) | kwargs

def test_review_invalid_row_cannot_poison_persistent_memory(isolated):
    data = row(topic=['not a string'])
    with pytest.raises((TypeError, ValueError)):
        ingest.apply([data], advance_pi=data['ts'])
    assert wl.load_log('life') == [], 'Invalid topic was appended before regeneration failed'
    assert host.load_cursors(str(isolated)).get('transcripts_pi') is None

def test_review_same_day_issue_update_is_not_deduplicated(isolated):
    for hour, status in ((9,'open'), (17,'closed')):
        ts=f'2026-09-01T{hour:02d}:00:00.000Z'
        issue={'identifier':'TEST-1','title':'Synthetic task','updatedAt':ts,'state':{'name':status}}
        with patch.object(linear,'_post',return_value={'issues':{'nodes':[issue]}}):
            item=linear.read('fake',None)[0]
        ingest.apply([row(item['uuid'], ts=ts, source='watari', status=status, note=status)])
    assert len(wl.load_log('life')) == 2, 'Second same-day update was skipped'
    assert json.loads(Path(wl.state_path('life')).read_text())['open_threads'] == []

def test_review_gmail_limit_does_not_skip_unread_older_messages(isolated):
    base=datetime(2026,9,1,tzinfo=timezone.utc)
    messages=[{'id':str(i),'internalDate':str(int((base+timedelta(minutes=i)).timestamp()*1000))} for i in range(51)]
    def fake_get(service,url,token):
        if '/messages?' in url:
            import urllib.parse
            after=int(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)['q'][0].split(':')[1])
            return {'messages':[{'id':m['id']} for m in reversed(messages) if int(m['internalDate'])//1000 > after]}
        return messages[int(url.split('/messages/')[1].split('?')[0])]
    with patch.object(cloud,'access_token',return_value='fake'), patch.object(google_connectors,'_get_json',side_effect=fake_get):
        first=google_connectors.gmail_read('2026-08-31T00:00:00.000Z')
        second=google_connectors.gmail_read(first[-1]['ts'])
    observed={r['meta']['id'] for r in first+second}
    assert len(observed)==51, f'First={len(first)}, second={len(second)}, missing={set(str(i) for i in range(51))-observed}'

def test_review_timestamp_sort_uses_instant_not_string(isolated):
    older=row('old',kind='fact',ts='2026-09-01T00:00:00Z',profile={'key':'answer','value':'old','mode':'always'})
    newer=row('new',kind='fact',ts='2026-09-01T00:00:00.100Z',profile={'key':'answer','value':'new','mode':'always'})
    ingest.apply([older,newer])
    profile=json.loads(Path(wl.state_path('life')).read_text())['profile']
    assert profile['answer']=='new', profile

def _session(root):
    root.mkdir()
    (root/'s.jsonl').write_text('\n'.join(json.dumps(x) for x in [
        {'type':'session','id':'S','cwd':'/synthetic'},
        {'type':'message','id':'M','timestamp':'2026-09-01T00:00:00.000Z',
         'message':{'role':'user','content':'Synthetic evidence'}}])+'\n')

class FakeStore(cloud.CloudStore):
    def __init__(self): self.data={}
    def append(self,name,text): self.data[name]=self.data.get(name,'')+text

def test_review_queue_write_failure_preserves_retry(isolated,tmp_path):
    root=tmp_path/'pi'; _session(root)
    worker=relay.Relay(str(root),'synthetic-review'); store=FakeStore(); worker._store=store
    original_open=builtins.open
    def failing_open(path,*args,**kwargs):
        if str(path).endswith('relay-queue.jsonl') and args and args[0]=='a':
            raise OSError('synthetic disk failure')
        return original_open(path,*args,**kwargs)
    with patch('builtins.open',side_effect=failing_open):
        with pytest.raises(OSError): worker._tick()
    restarted=relay.Relay(str(root),'synthetic-review'); restarted._store=store
    restarted._tick()
    assert store.data, 'Offsets advanced before queue append; retry found no message'

def test_review_memory_in_parent_repo_does_not_commit_sibling_files(isolated,tmp_path):
    repo=tmp_path/'parent'; repo.mkdir(); memory=repo/'memory'; memory.mkdir()
    def git(*args): return subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True,check=True)
    git('init'); git('config','user.email','review@example.invalid'); git('config','user.name','Synthetic Reviewer')
    (repo/'unrelated.txt').write_text('original'); git('add','unrelated.txt'); git('commit','-m','baseline')
    (repo/'unrelated.txt').write_text('private unrelated change')
    (memory/'memory.txt').write_text('memory')
    git_sync.sync_before_read(str(memory))
    assert git('show','HEAD:unrelated.txt').stdout=='original', 'Sibling content was committed by memory read'

def test_review_other_slack_bot_not_accepted_as_watari(isolated):
    responses=[{'ok':True,'user':'user','team':'Synthetic','team_id':'T1'},
               {'ok':True,'user':'DifferentBot','bot_id':'B-OTHER','team':'Synthetic','team_id':'T1'}]
    with patch.object(slack,'_auth_test',side_effect=responses):
        ok,message=slack.verify_credentials({'api_key':'xoxp-fake','bot_token':'xoxb-fake'})
    assert not ok, message

def test_review_unknown_version_and_source_are_rejected(isolated):
    errors=ingest.validate([row(source='undeclared-service',schema_version=999)],False)
    assert errors, 'Unknown format/source accepted silently'

def test_review_unknown_pi_session_version_fails_closed(isolated,tmp_path):
    root=tmp_path/'pi'; _session(root)
    path=root/'s.jsonl'; lines=path.read_text().splitlines()
    header=json.loads(lines[0]); header['version']=999
    path.write_text(json.dumps(header)+'\n'+'\n'.join(lines[1:])+'\n')
    ok,rows=extract.scan_pi_store(str(root),None)
    assert not ok and not rows, f'Unsupported version 999 accepted: readable={ok}, rows={len(rows)}'

@pytest.mark.parametrize('field,value', [
    ('topic', ['bad']), ('summary', {}), ('note', ['bad']), ('refs', []),
    ('tags', [1]), ('kind', []), ('profile', {'key': [], 'value': 'x', 'mode': 'always'}),
    ('heat', True), ('status', ['closed']), ('source', 'undeclared-service'),
])
def test_malformed_fields_rejected_before_any_write(isolated, field, value):
    with pytest.raises(ValueError):
        ingest.apply([row(**{field: value})])
    assert wl.load_log('life') == []
    assert not Path(host.host_path(str(isolated))).exists()


def test_concurrent_ingest_serializes_validation_and_commit(isolated):
    entered = threading.Event()
    release = threading.Event()
    errors = []
    real_keys = ingest.existing_dedup_keys
    def keys():
        result = real_keys()
        if threading.current_thread().name == 'older':
            entered.set()
            assert release.wait(5)
        return result
    def writer(uid, ts):
        try:
            ingest.apply([row(uid, ts=ts)], advance_pi=ts)
        except Exception as error:
            errors.append(error)
    with patch.object(ingest, 'existing_dedup_keys', side_effect=keys):
        old = threading.Thread(target=writer, name='older', args=('old', '2026-09-01T00:00:00.000Z'))
        new = threading.Thread(target=writer, args=('new', '2026-09-02T00:00:00.000Z'))
        old.start()
        assert entered.wait(5)
        new.start()
        new.join(.15)
        release.set()
        old.join(5)
        new.join(5)
    assert not old.is_alive() and not new.is_alive()
    assert not errors
    assert host.load_cursors(str(isolated))['transcripts_pi'] == '2026-09-02T00:00:00.000Z'
    assert len(wl.load_log('life')) == 2


def test_generation_error_leaves_memory_and_cursor_untouched(isolated):
    with patch.object(regen_state, 'fold_life', side_effect=ValueError('synthetic failure')):
        with pytest.raises(ValueError):
            ingest.apply([row()], advance_pi=row()['ts'])
    assert wl.load_log('life') == []
    assert not Path(host.host_path(str(isolated))).exists()


def test_interrupted_commit_recovers_before_next_read(isolated):
    from watari_cli import storage
    real_write = storage.atomic_write_text
    failed = False
    def write(path, text):
        nonlocal failed
        if str(path).endswith('life/state.json') and not failed:
            failed = True
            raise OSError('synthetic interruption')
        return real_write(path, text)
    with patch.object(storage, 'atomic_write_text', side_effect=write):
        with pytest.raises(OSError):
            ingest.apply([row()], advance_pi=row()['ts'])
    assert len(wl.load_log('life')) == 1
    assert host.load_cursors(str(isolated))['transcripts_pi'] == row()['ts']
    ingest.apply([row()])
    assert len(wl.load_log('life')) == 1


def test_prune_never_overwrites_a_changed_snapshot(isolated):
    now = datetime.now(timezone.utc)
    old = wl.fmt_ts(now - timedelta(days=1))
    name = 'transcripts-origin.jsonl'
    class Store(cloud.CloudStore):
        def __init__(self):
            self.content = json.dumps({'ts': old, 'text': 'old'})+'\n'
        def list(self): return [{'name': name}]
        def snapshot(self, name):
            original = self.content
            self.content += json.dumps({'ts': wl.fmt_ts(now), 'text': 'new'})+'\n'
            return original, original
        def replace_if_unchanged(self, name, revision, text):
            if self.content != revision: return False
            self.content = text
            return True
        def read(self, name): return self.snapshot(name)[0]
        def write(self, name, text): self.content = text
        def delete(self, name): self.content = ''
    store = Store()
    with patch.object(cloud, 'get_store', return_value=store), patch.object(host, 'all_hosts', return_value=[
        {'machine_id': 'receiver', 'cursors': {'cloud_origin': old}}
    ]):
        relay.prune_cloud(str(isolated))
    assert 'new' in store.content

@pytest.mark.parametrize('service', ['gmail', 'calendar', 'gdrive'])
def test_google_read_follows_next_page(service, isolated):
    calls = []
    def get(name, url, token):
        calls.append(url)
        if '/messages/' in url:
            return {'internalDate': '1788220800000'}
        second = 'pageToken=next' in url
        item = {'id': 'b' if second else 'a', 'updated': row()['ts'], 'modifiedTime': row()['ts']}
        key = {'gmail':'messages', 'calendar':'items', 'gdrive':'files'}[name]
        return {key:[item], **({} if second else {'nextPageToken':'next'})}
    with patch.object(cloud, 'access_token', return_value='fake'), patch.object(google_connectors, '_get_json', side_effect=get):
        result = getattr(google_connectors, f'{service}_read')(None)
    assert len(result) == 2
    assert any('pageToken=next' in u for u in calls)


def test_linear_follows_update_pages(isolated):
    pages = [
        {'issues': {'nodes': [{'identifier':'T-1','updatedAt':row()['ts']}], 'pageInfo': {'hasNextPage': True, 'endCursor':'next'}}},
        {'issues': {'nodes': [{'identifier':'T-2','updatedAt':row()['ts']}], 'pageInfo': {'hasNextPage': False}}},
    ]
    with patch.object(linear, '_post', side_effect=pages) as request:
        assert len(linear.read('fake', None)) == 2
        assert request.call_args.args[2]['after'] == 'next'


def test_unknown_runtime_is_rejected_without_execution():
    from watari_cli.cli import _runtime_base
    with pytest.raises(ValueError):
        _runtime_base('unknown --unsafe')


def test_drive_replace_uses_snapshot_etag_and_rejects_conflict(isolated):
    store = cloud.DriveAppDataStore()
    with patch.object(store, '_headers', return_value={}), patch.object(cloud, '_http', return_value=(412, b'')) as request:
        assert store.replace_if_unchanged('synthetic', ('file-id', '"v1"'), 'new') is False
    assert request.call_args.args[2]['If-Match'] == '"v1"'


def test_drive_missing_revision_never_performs_unsafe_write(isolated):
    store = cloud.DriveAppDataStore()
    with patch.object(store, '_headers', return_value={}), patch.object(store, '_find', return_value={'id':'file-id'}), \
         patch.object(cloud, '_http_with_headers', return_value=(200, b'old', {}), create=True):
        with pytest.raises(cloud.CloudError):
            store.snapshot('synthetic')


def test_invalid_config_is_not_silently_replaced(isolated):
    path = Path(config._config_file())
    path.parent.mkdir(parents=True)
    original = '{invalid'
    path.write_text(original)
    with pytest.raises(ValueError):
        config.save_config(performance='fast')
    assert path.read_text() == original


def test_unknown_persisted_version_is_rejected(isolated):
    Path(wl.log_path('life')).write_text(json.dumps(row(schema_version=999)) + '\n')
    with pytest.raises(ValueError):
        wl.load_log('life')


def test_timestamp_ties_are_not_split_across_transcript_batches():
    from watari_cli.transcripts.common import unify
    rows = [{'ts': row()['ts'], 'uuid': str(i)} for i in range(4)]
    assert len(unify(rows, None, max_rows=2)) == 4


def test_gmail_timestamp_keeps_subsecond_precision():
    assert google_connectors._iso_from_epoch_millis(1788220800123).endswith('.123Z')


def test_connector_registration_serializes_read_modify_write(isolated):
    entered, release = threading.Event(), threading.Event()
    real = config.load_connectors
    errors = []
    def load():
        result = real()
        if threading.current_thread().name == 'first-config-writer':
            entered.set()
            assert release.wait(5)
        return result
    def register(name):
        try:
            config.save_connector({'name':name, 'scope':'local'})
        except Exception as e:
            errors.append(e)
    with patch.object(config, 'load_connectors', side_effect=load):
        one = threading.Thread(target=register, name='first-config-writer', args=('one',))
        two = threading.Thread(target=register, args=('two',))
        one.start(); assert entered.wait(5)
        two.start(); two.join(.15); release.set()
        one.join(5); two.join(5)
    assert not errors
    assert {c['name'] for c in config.load_connectors()} == {'one', 'two'}


def test_regen_command_holds_memory_lock_for_read_and_write(isolated):
    from watari_cli import cli, storage
    from types import SimpleNamespace
    active = []
    @contextlib.contextmanager
    def lock(resource, **kwargs):
        active.append(resource)
        try: yield
        finally: active.pop()
    real = regen_state.regen
    def generate(*args, **kwargs):
        assert str(isolated) in active
        return real(*args, **kwargs)
    with patch.object(storage, 'file_lock', side_effect=lock), patch.object(regen_state, 'regen', side_effect=generate):
        assert cli.cmd_regen(SimpleNamespace(home=str(isolated), now=None, check=False)) == 0


def test_organize_reads_assistant_text_only_as_context(isolated, tmp_path):
    root = tmp_path/'pi'; _session(root)
    with (root/'s.jsonl').open('a') as f:
        f.write(json.dumps({'type':'message', 'id':'A', 'timestamp':'2026-09-01T00:00:01.000Z',
                           'message': {'role':'assistant', 'content':[{'type':'text','text':'proposal'},
                                       {'type':'thinking','thinking':'not evidence'}]}})+'\n')
    with patch.object(extract, 'PI_STORE', str(root)), patch.object(cloud, 'get_store', return_value=None):
        result = extract.run()
    assert [r['role'] for r in result['messages']] == ['user', 'assistant']
    assert result['messages'][1]['text'] == 'proposal'


def test_background_failure_records_only_exit_status(isolated):
    from watari_cli import cli
    class Process:
        pid = 123
        def wait(self): return 7
    path = Path(os.environ['XDG_STATE_HOME'])/'dream-result.json'
    path.parent.mkdir(parents=True)
    cli._record_dream_result(Process(), str(path), str(isolated))
    result = json.loads(path.read_text())
    assert result['status'] == 'failed' and result['exit_code'] == 7
    assert 'text' not in result and 'output' not in result


def test_partial_queue_tail_does_not_corrupt_retried_message(isolated, tmp_path):
    root = tmp_path/'pi'; _session(root)
    Path(relay._queue_path()).write_text('{"partial":')
    worker = relay.Relay(str(root), 'synthetic-review'); worker._store = FakeStore()
    worker._tick()
    lines = worker._store.data['transcripts-synthetic-review.jsonl'].splitlines()
    assert [json.loads(line)['text'] for line in lines] == ['Synthetic evidence']


def test_same_sender_credentials_are_pinned_at_connection(isolated):
    credentials = {'api_key':'xoxp-fake', 'bot_token':'xoxb-fake'}
    responses = [{'ok':True, 'user':'person', 'user_id':'UP', 'team_id':'T1'},
                 {'ok':True, 'user':'watari', 'user_id':'UW', 'bot_id':'B1', 'team_id':'T1'}]
    with patch.object(slack, '_auth_test', side_effect=responses):
        assert slack.verify_credentials(credentials)[0]
    assert credentials['identity']['bot_id'] == 'B1'
    assert credentials['identity']['team_id'] == 'T1'


def test_importing_service_adapters_does_not_select_a_memory_home():
    import sys
    result = subprocess.run([sys.executable, '-c',
        "import sys; from watari_cli import linear, google_connectors; "
        "assert 'watari_cli.engine.watari_lib' not in sys.modules"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_slack_since_uses_instant_not_iso_spelling(isolated):
    message = {'ts':'1788220800.100000', 'channel':{'id':'C1'}, 'text':'new'}
    with patch.object(slack, '_auth_test', return_value={'user_id':'U1'}), patch.object(slack, '_search', return_value=[message]):
        assert len(slack.read('xoxp-fake', '2026-09-01T00:00:00Z')) == 1


def test_two_processes_append_without_losing_either_update(isolated):
    import sys
    code = '''
import sys
from watari_cli.engine import ingest
for i in range(5):
    ingest.apply([{'ts':'2026-09-01T00:00:00.000Z', 'source':'watari', 'kind':'fact',
                   'summary':'synthetic', 'refs':{'uuid':sys.argv[1]+str(i)}}])
'''
    env = dict(os.environ, WATARI_HOME=str(isolated))
    processes = [subprocess.Popen([sys.executable, '-c', code, name], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for name in ('one-', 'two-')]
    try:
        for process in processes:
            out, err = process.communicate(timeout=15)
            assert process.returncode == 0, out + err
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill(); process.wait()
    assert len(wl.load_log('life')) == 10
    assert len({r['refs']['uuid'] for r in wl.load_log('life')}) == 10


@pytest.mark.parametrize('payload', [
    {'version':999, 'files':{'life/log.jsonl':'bad'}},
    {'version':1, 'files':{'../outside':'bad'}},
])
def test_unsafe_recovery_journal_writes_nothing(isolated, payload):
    from watari_cli import storage
    (isolated/storage.JOURNAL).write_text(json.dumps(payload))
    with pytest.raises(RuntimeError):
        storage.recover(str(isolated))
    assert Path(wl.log_path('life')).read_text() == ''
    assert not (isolated.parent/'outside').exists()


def test_pagination_cycle_fails_instead_of_returning_a_partial_batch():
    from watari_cli import connector_http
    with pytest.raises(connector_http.ConnectorError):
        connector_http.paged_items(lambda _: {'items':[1], 'nextPageToken':'same'}, 'items')
