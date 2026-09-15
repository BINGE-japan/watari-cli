"""Synthetic-only contracts for fixed memory operations (no model/MCP/live services)."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from watari_cli import memory_operations as ops
from watari_cli.engine import ingest, watari_lib as wl

TS = '2026-01-02T00:00:00.000Z'


def message(uuid='u1', role='user', ts=TS, store='pi'):
    return dict(uuid=uuid, role=role, ts=ts, store=store, text='Synthetic preference',
                session='sample-session', cwd='/workspace/example', machine='sample-pc',
                computer='linux', runtime='native')


def scan(messages=None, readable=True):
    messages = messages if messages is not None else [message()]
    return {'generated': TS, 'stores': {'pi': {'cursor': None, 'readable': readable,
            'count': len(messages), 'max_ts': messages[-1]['ts'] if messages else None,
            'truncated': False}}, 'messages': messages}


@pytest.fixture
def memory(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    home = tmp_path / 'memory'
    for genre in ('life', 'learning'):
        (home / genre).mkdir(parents=True)
        (home / genre / 'log.jsonl').write_text('')
    monkeypatch.setattr(wl, 'MEM', str(home))
    monkeypatch.setattr(ingest, 'MEM', str(home))
    ingest.apply([])
    monkeypatch.setattr(ops.git_sync, 'sync_after_write', lambda home: None)
    return home


def decisions(uuid='u1'):
    return [{'uuid': uuid, 'rows': [{'kind': 'fact', 'summary': 'Synthetic user preference.', 'note': 'Prefers short answers.',
             'profile': {'key': 'response_style', 'value': 'Short answers.', 'mode': 'always'}}]}]


def test_batch_keeps_equal_time_group_and_never_advances_unshown_messages():
    messages = [message('u1'), message('u2'), message('u3', ts='2026-01-03T00:00:00Z')]
    result = ops.make_batch(scan(messages), max_messages=1)
    assert [m['uuid'] for m in result['messages']] == ['u1', 'u2']
    assert result['stores']['pi']['max_ts'] == TS
    assert result['stores']['pi']['truncated'] is True


def test_failed_source_is_retained_without_advancement(memory):
    batch = ops.make_batch(scan(readable=False))
    result = ops.save_batch(batch, decisions())
    assert result['saved'] and result['checked']
    assert wl.load_cursors()['transcripts_pi'] is None
    assert result['incomplete_sources'] == ['pi']


def test_requires_decision_for_every_user_not_assistant(memory):
    batch = ops.make_batch(scan([message(), message('a1', 'assistant')]))
    before = (memory / 'life/log.jsonl').read_bytes()
    with pytest.raises(ValueError):
        ops.save_batch(batch, [])
    assert (memory / 'life/log.jsonl').read_bytes() == before
    assert ops.save_batch(batch, decisions())['checked']


@pytest.mark.parametrize('mutation', ['refs', 'ts', 'source', 'unknown'])
def test_model_cannot_supply_origin_or_unknown_fields(memory, mutation):
    data = decisions()
    data[0]['rows'][0][mutation] = 'forged'
    with pytest.raises(ValueError):
        ops.save_batch(ops.make_batch(scan()), data)
    assert (memory / 'life/log.jsonl').read_text() == ''


def test_origin_bound_to_observed_message_and_save_replay_is_deduplicated(memory):
    batch = ops.make_batch(scan())
    first = ops.save_batch(batch, decisions())
    assert first['saved'] and first['checked']
    row = json.loads((memory / 'life/log.jsonl').read_text())
    assert row['refs']['uuid'] == 'u1'
    assert row['refs']['computer'] == 'linux'
    assert row['ts'] == TS
    assert wl.load_cursors()['transcripts_pi'] == TS
    ops.save_batch(batch, decisions())
    assert len((memory / 'life/log.jsonl').read_text().splitlines()) == 1


def test_empty_selection_can_finish_but_does_not_create_fake_facts(memory):
    result = ops.save_batch(ops.make_batch(scan()), [{'uuid': 'u1', 'rows': []}])
    assert result['checked']
    assert (memory / 'life/log.jsonl').read_text() == ''
    assert wl.load_cursors()['transcripts_pi'] == TS


def test_assistant_or_unknown_evidence_and_duplicate_decisions_rejected(memory):
    batch = ops.make_batch(scan([message(), message('a1', 'assistant')]))
    for data in (decisions('a1'), decisions('missing'), decisions() + decisions()):
        with pytest.raises(ValueError):
            ops.save_batch(batch, data)
    assert (memory / 'life/log.jsonl').read_text() == ''


def test_duplicate_kind_per_message_is_rejected_instead_of_silently_lost(memory):
    data = decisions()
    data[0]['rows'].append(copy.deepcopy(data[0]['rows'][0]))
    with pytest.raises(ValueError):
        ops.save_batch(ops.make_batch(scan()), data)


def test_get_exact_topic_includes_closed_history_and_origin(memory):
    rows = [{'ts': TS, 'source': 'watari', 'kind': 'thread', 'topic': 'Example task',
             'summary': 'Synthetic completion.', 'note': 'Finished.', 'status': 'closed', 'refs': {'uuid': 'r1', 'computer': 'mac'}}]
    ingest.apply(rows)
    result = ops.get_memory('thread', 'Example task')
    assert result['rows'][0]['status'] == 'closed'
    assert result['rows'][0]['refs']['computer'] == 'mac'
    assert ops.get_memory('thread', '../other')['rows'] == []


def test_reject_unknown_batch_version_and_oversized_first_time_group(memory):
    batch = ops.make_batch(scan())
    batch['version'] = 999
    with pytest.raises(ValueError):
        ops.save_batch(batch, decisions())
    with pytest.raises(ValueError):
        ops.make_batch(scan(), max_bytes=50)


def test_sync_warning_is_not_reported_as_verified_sync(memory):
    def warn(home):
        import sys
        print('Synthetic sync failure', file=sys.stderr)
    with patch.object(ops.git_sync, 'sync_after_write', warn):
        result = ops.save_batch(ops.make_batch(scan()), decisions())
    assert result['saved']
    assert result['sync'] == 'warning'
    assert result['warnings'] == 'Synthetic sync failure'


def test_current_input_batch_does_not_advance_conversation_read_position(memory):
    batch = ops.current_batch(message())
    assert ops.save_batch(batch, decisions())['saved']
    assert wl.load_cursors()['transcripts_pi'] is None


def test_get_paginates_without_dumping_all_history(memory):
    for i in range(4):
        rows = [{'ts': TS, 'source': 'watari', 'kind': 'thread', 'topic': 'Example',
                 'summary': 'Synthetic change.', 'note': str(i), 'refs': {'uuid': f'h{i}'}}]
        ingest.apply(rows)
    result = ops.get_memory('thread', 'Example', limit=2)
    assert len(result['rows']) == 2 and result['next_offset'] == 2
    assert ops.get_memory('thread', 'Example', limit=2, offset=2)['next_offset'] is None


def test_post_save_verification_failure_preserves_saved_status(memory):
    with patch.object(ops.audit, 'audit_report', side_effect=ValueError('Synthetic inspection failure')):
        result = ops.save_batch(ops.make_batch(scan()), decisions())
    assert result['saved'] and not result['checked']
    assert (memory / 'life/log.jsonl').read_text()


def test_changed_cursor_refuses_old_batch_without_writing(memory):
    batch = ops.make_batch(scan())
    ingest.apply([], advance_pi='2026-01-04T00:00:00Z')
    with pytest.raises(ValueError):
        ops.save_batch(batch, decisions())
    assert (memory / 'life/log.jsonl').read_text() == ''


def test_cloud_advancement_uses_only_returned_readable_source(memory):
    a, b = message('u1', store='cloud_sample-a'), message('u2', store='cloud_sample-b')
    snapshot = scan([a, b])
    info = snapshot['stores'].pop('pi')
    snapshot['stores'] = {'cloud_sample-a':info, 'cloud_sample-b':{**info, 'readable':False}}
    batch = ops.make_batch(snapshot)
    result = ops.save_batch(batch, decisions() + [{'uuid':'u2', 'rows':[]}])
    assert result['saved']
    assert wl.load_cursors()['cloud_sample-a'] == TS
    assert wl.load_cursors().get('cloud_sample-b') is None


def test_images_are_not_copied_into_batch_or_claimed_read():
    m = message()
    m['text'] = [{'type':'text', 'text':'Synthetic caption'}, {'type':'image', 'data':'synthetic-binary'}]
    batch = ops.current_batch(m)
    assert batch['messages'][0]['omitted_images'] is True
    assert 'synthetic-binary' not in json.dumps(batch)


def test_get_canonical_learning_domain_finds_legacy_alias(memory):
    (memory / 'learning/aliases.json').write_text(json.dumps({'old-domain':'science'}))
    ingest.apply([{'ts':TS, 'source':'watari', 'kind':'study', 'domain':'old-domain',
                   'topic':'Example concept', 'summary':'Synthetic learning.', 'note':'Understands the example.',
                   'mastery':1, 'refs':{'uuid':'study-1'}}], allow_new_domain=True)
    result = ops.get_memory('study', 'Example concept', domain='science')
    assert result['rows'][0]['refs']['uuid'] == 'study-1'
