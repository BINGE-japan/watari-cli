"""Regression coverage for real Drive v3 responses: synthetic data, no network."""
import contextlib
import io
import json
from unittest.mock import patch

import pytest

from watari_cli import cloud, relay


@pytest.fixture(autouse=True)
def isolated_network_and_config(tmp_path, monkeypatch):
    monkeypatch.setenv('WATARI_HOME', str(tmp_path / 'memory'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    with patch('urllib.request.urlopen', side_effect=AssertionError('live network forbidden')):
        yield


@pytest.fixture
def store():
    with patch.object(cloud.DriveAppDataStore, '_headers', return_value={}), \
         patch.object(cloud.DriveAppDataStore, '_find', return_value={'id': 'fixture-file'}):
        yield cloud.DriveAppDataStore()


def metadata(etag='"strong-v2"', version='1'):
    return 200, json.dumps({'id': 'fixture-file', 'etag': etag, 'version': version}).encode(), {}


@pytest.mark.parametrize('v3_headers', [{}, {'ETag': 'W/"weak"'}])
def test_snapshot_falls_back_to_v2_strong_etag_with_matching_content(store, v3_headers):
    with patch.object(cloud, '_http_with_headers', side_effect=[
        (200, b'old-v3\n', v3_headers), metadata(),
        (200, b'current-v2\n', {'eTaG': '"different-media-etag"'}), metadata(),
    ]) as request:
        content, revision = store.snapshot('synthetic')
    assert content == 'current-v2\n'  # Never use the earlier v3 body.
    assert revision == ('fixture-file', '"strong-v2"', 'v2')
    assert [call.args[1] for call in request.call_args_list[1:]] == [
        'https://www.googleapis.com/drive/v2/files/fixture-file?fields=id,etag,version',
        'https://www.googleapis.com/drive/v2/files/fixture-file?alt=media',
        'https://www.googleapis.com/drive/v2/files/fixture-file?fields=id,etag,version',
    ]


@pytest.mark.parametrize('after', [metadata('"changed"', '2'), metadata(version='2')])
def test_v2_metadata_change_during_read_rejects_snapshot(store, after):
    with patch.object(cloud, '_http_with_headers', side_effect=[
        (200, b'old-v3', {}), metadata(), (200, b'content', {}), after,
    ]), patch.object(cloud, '_http') as write:
        with pytest.raises(cloud.CloudError):
            store.append('synthetic', 'new')
    write.assert_not_called()


@pytest.mark.parametrize('status', [200, 412, 404])
def test_v2_snapshot_update_uses_v2_endpoint_and_if_match(store, status):
    with patch.object(cloud, '_http', return_value=(status, b'{}')) as request:
        result = store.replace_if_unchanged(
            'synthetic', ('fixture-file', '"strong-v2"', 'v2'), 'new\n')
    assert result is (status == 200)
    method, url, headers, body = request.call_args.args
    assert method == 'PATCH'
    assert url == 'https://www.googleapis.com/upload/drive/v2/files/fixture-file?uploadType=media'
    assert headers['If-Match'] == '"strong-v2"'
    assert body == b'new\n'


@pytest.mark.parametrize('v2_response', [
    (200, b'{}', {}),
    metadata('W/"weak"'),
    (206, b'partial', {'ETag': '"strong"'}),
    (403, b'forbidden', {'ETag': '"strong"'}),
])
def test_missing_or_unusable_v2_revision_still_fails_closed(store, v2_response):
    with patch.object(cloud, '_http_with_headers', side_effect=[
        (200, b'old', {}), v2_response,
    ]), patch.object(cloud, '_http') as write:
        with pytest.raises(cloud.CloudError):
            store.append('synthetic', 'new')
    write.assert_not_called()


@pytest.mark.parametrize('status', [206, 403, 500])
def test_v2_content_read_must_be_complete_success(store, status):
    with patch.object(cloud, '_http_with_headers', side_effect=[
        (200, b'v3', {}), metadata(), (status, b'partial-or-error', {}),
    ]), patch.object(cloud, '_http') as write:
        with pytest.raises(cloud.CloudError):
            store.append('synthetic', 'new')
    write.assert_not_called()


def test_v3_read_error_is_not_hidden_by_fallback(store):
    with patch.object(cloud, '_http_with_headers', return_value=(403, b'error', {})) as request:
        with pytest.raises(cloud.CloudError):
            store.snapshot('synthetic')
    assert request.call_count == 1


def test_unknown_revision_api_is_rejected_without_request(store):
    with patch.object(cloud, '_http') as request:
        with pytest.raises(cloud.CloudError):
            store.replace_if_unchanged('synthetic', ('fixture-file', '"etag"', 'v99'), 'new')
    request.assert_not_called()


def test_duplicate_failure_shows_data_repair_not_relogin(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path))
    with patch.object(cloud, '_http', return_value=(200, b'{"files":[{"id":"a"},{"id":"b"}]}')), \
         patch.object(cloud.DriveAppDataStore, '_headers', return_value={}):
        s = cloud.DriveAppDataStore()
        r = relay.Relay(str(tmp_path / 'sessions'), 'synthetic')
        r._store = s
        with open(relay._queue_path(), 'w') as f:
            f.write('synthetic queue\n')
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            r._flush()
        assert '同名の同期データが複数' in output.getvalue()
        assert 'watari auth' not in output.getvalue()
        with open(relay._queue_path()) as f:
            assert f.read() == 'synthetic queue\n'


def test_v3_strong_etag_needs_no_fallback(store):
    with patch.object(cloud, '_http_with_headers', return_value=(
        200, b'current', {'ETag': '\"v3\"'})) as request:
        assert store.snapshot('synthetic') == ('current', ('fixture-file', '\"v3\"'))
    assert request.call_count == 1


def test_v2_conflict_retains_queue_and_next_attempt_succeeds(store, tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path))
    r = relay.Relay(str(tmp_path / 'sessions'), 'synthetic')
    r._store = store
    with open(relay._queue_path(), 'w') as f:
        f.write('pending\n')
    with patch.object(cloud, '_http_with_headers', side_effect=[
        (200, b'old-v3\n', {}), metadata('"v1"'), (200, b'old-v2\n', {}), metadata('"v1"'),
        (200, b'old-v3\n', {}), metadata('"v2"'), (200, b'concurrent\n', {}), metadata('"v2"'),
    ]), patch.object(cloud, '_http', side_effect=[(412, b''), (200, b'{}')]) as write:
        r._flush()
        with open(relay._queue_path()) as f:
            assert f.read() == 'pending\n'
        r._flush()
        with open(relay._queue_path()) as f:
            assert f.read() == ''
    assert write.call_count == 2
    assert write.call_args.args[2]['If-Match'] == '\"v2\"'
    assert write.call_args.args[3] == b'concurrent\npending\n'
