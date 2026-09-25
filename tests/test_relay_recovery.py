"""Drive alert/recovery regressions: synthetic sessions and mocked HTTP only."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from watari_cli import cloud, config, relay


class FakeStore(cloud.CloudStore):
    def __init__(self):
        self.sent = []
        self.error = None

    def append(self, name, text):
        if self.error:
            raise self.error
        cloud.check_live_authorization()  # real classification, mocked HTTP transport
        self.sent.append((name, text))


class DriveRecoveryTest(unittest.TestCase):
    def setUp(self):
        stack = self.stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        stack.enter_context(patch.dict('os.environ', {
            'XDG_CONFIG_HOME': str(root / 'config'),
            'XDG_STATE_HOME': str(root / 'state'),
            'WATARI_HOME': str(root / 'memory'),
            'WATARI_GOOGLE_CLIENT_ID': '',
            'WATARI_GOOGLE_CLIENT_SECRET': '',
        }))
        self.pi = root / 'sessions'
        self.pi.mkdir()
        self.session = self.pi / 'synthetic.jsonl'
        self.session.write_text(json.dumps({
            'type': 'session', 'version': 3, 'id': 'synthetic', 'cwd': '/synthetic',
        }) + '\n')
        config.save_config(google={
            'client_id': 'synthetic-client', 'client_secret': 'synthetic-secret',
            'refresh_token': 'synthetic-refresh',
        })
        self.http = stack.enter_context(patch.object(cloud, '_http', return_value=(
            200, b'{"access_token":"synthetic-access"}')))
        self.store = FakeStore()
        self.get_store = stack.enter_context(patch.object(
            cloud, 'get_store', side_effect=lambda: self.store if cloud.is_authorized() else None))
        stack.enter_context(patch('threading.Thread.start'))
        # Patch the standard clock so both old and fixed implementations can run.
        self.clock = stack.enter_context(patch('time.monotonic', return_value=100.0))
        self.err = stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.worker = relay.Relay(str(self.pi), 'synthetic-machine')

    def add_message(self, text='synthetic message'):
        with self.session.open('a') as f:
            f.write(json.dumps({
                'type': 'message', 'id': text, 'timestamp': '2026-01-01T00:00:00Z',
                'message': {'role': 'user', 'content': text},
            }) + '\n')

    def queue(self):
        return Path(relay._queue_path()).read_text()

    def test_start_prepares_delivery_without_network_probe(self):
        self.http.side_effect = cloud.CloudError('synthetic offline at startup')
        self.worker.start()
        self.http.assert_not_called()
        self.assertIs(self.worker._store, self.store)
        self.assertEqual(self.err.getvalue(), '')

    def test_temporary_network_failure_must_not_request_reauthentication(self):
        self.http.side_effect = cloud.CloudError('synthetic network outage')
        self.worker.start()
        self.add_message()
        self.worker._tick()
        self.assertNotIn('watari auth', self.err.getvalue())
        self.assertIn('自動', self.err.getvalue())
        self.assertEqual(self.store.sent, [])
        self.assertIn('synthetic message', self.queue())
        self.assertTrue(self.worker._enabled)

    def test_startup_network_recovery_must_resume_delivery(self):
        self.http.side_effect = cloud.CloudError('synthetic network outage')
        self.worker.start()
        self.add_message()
        self.worker._tick()
        queued = self.queue()
        self.assertIn('synthetic message', queued)
        self.http.side_effect = None
        self.clock.return_value += 600
        self.worker._tick()
        self.assertEqual(self.store.sent, [(self.worker.cloud_name, queued)])
        self.assertEqual(self.queue(), '')
        self.assertEqual(self.err.getvalue().count('同期が再開しました'), 1)
        self.worker._tick()
        self.assertEqual(len(self.store.sent), 1)
        self.assertEqual(self.err.getvalue().count('同期が再開しました'), 1)

    def test_http_server_and_unknown_errors_must_not_request_reauthentication(self):
        for status, body in ((503, b'{"error":"temporarily_unavailable"}'),
                             (429, b'{"error":"rate_limit_exceeded"}'),
                             (500, b'{"error":"invalid_grant"}'),
                             (400, b'{"error":"unknown_error"}'),
                             (200, b'not-json'), (200, b'[]'),
                             (200, b'{"access_token":null}')):
            with self.subTest(status=status, body=body):
                self.http.return_value = status, body
                self.err.seek(0); self.err.truncate()
                worker = relay.Relay(str(self.pi), 'synthetic-machine')
                worker.start()
                Path(relay._queue_path()).write_text('synthetic pending\n')
                worker._flush()
                self.assertNotIn('watari auth', self.err.getvalue())
                self.assertIn('自動', self.err.getvalue())
                self.assertEqual(self.store.sent, [])
                self.assertEqual(self.queue(), 'synthetic pending\n')

    def test_revoked_or_missing_credentials_require_auth_and_can_recover(self):
        for code in ('invalid_grant', 'invalid_client', 'deleted_client', 'missing_token'):
            with self.subTest(code=code):
                self.err.seek(0); self.err.truncate()
                config.save_config(google={
                    'client_id': 'synthetic-client', 'client_secret': 'synthetic-secret',
                    'refresh_token': None if code == 'missing_token' else 'synthetic-refresh',
                })
                self.http.return_value = 400, json.dumps({'error': code}).encode()
                worker = relay.Relay(str(self.pi), 'synthetic-machine')
                worker.start()
                sent_before = len(self.store.sent)
                Path(relay._queue_path()).write_text('synthetic pending\n')
                worker._flush()
                self.assertIn('watari auth', self.err.getvalue())
                self.assertEqual(len(self.store.sent), sent_before)
                self.assertEqual(self.queue(), 'synthetic pending\n')
                worker._flush()
                self.assertEqual(self.err.getvalue().count('!'), 1)
                config.save_config(google={
                    'client_id': 'synthetic-client', 'client_secret': 'synthetic-secret',
                    'refresh_token': 'synthetic-new-refresh',
                })
                self.http.return_value = 200, b'{"access_token":"synthetic-access"}'
                self.clock.return_value += 600
                worker._flush()
                self.assertEqual(self.queue(), '')
                self.assertEqual(self.store.sent[-1][1], 'synthetic pending\n')

    def test_retries_back_off_but_keep_collecting_messages(self):
        self.http.side_effect = cloud.CloudError('synthetic outage')
        self.worker.start()
        self.assertEqual(self.http.call_count, 0)
        self.add_message('first')
        self.worker._tick()
        self.assertEqual(self.http.call_count, 1)
        self.clock.return_value = 104
        self.add_message('second')
        self.worker._tick()
        self.assertEqual(self.http.call_count, 1)
        self.clock.return_value = 105
        self.worker._tick()
        self.assertEqual(self.http.call_count, 2)
        self.clock.return_value = 114
        self.worker._tick()
        self.assertEqual(self.http.call_count, 2)
        self.clock.return_value = 115
        self.worker._tick()
        self.assertEqual(self.http.call_count, 3)
        self.assertIn('first', self.queue())
        self.assertIn('second', self.queue())
        self.assertEqual(self.err.getvalue().count('!'), 1)

    def test_retry_delay_is_capped_and_resets_only_after_delivery(self):
        self.http.side_effect = cloud.CloudError('synthetic outage')
        self.worker.start()
        self.add_message()
        self.worker._tick()
        elapsed = 100.0
        for delay in (5, 10, 20, 40, 80, 160, 300, 300):
            before = self.http.call_count
            elapsed += delay
            self.clock.return_value = elapsed - 1
            self.worker._tick()
            self.assertEqual(self.http.call_count, before)
            self.clock.return_value = elapsed
            self.worker._tick()
            self.assertEqual(self.http.call_count, before + 1)
        self.assertEqual(self.err.getvalue().count('!'), 1)
        self.http.side_effect = None
        self.store.error = cloud.CloudError('synthetic upload outage')
        self.clock.return_value += 300
        self.worker._tick()
        self.assertNotIn('同期が再開しました', self.err.getvalue())
        self.assertIn('synthetic message', self.queue())
        self.clock.return_value += 300
        self.store.error = None
        self.worker._tick()
        self.assertEqual(self.queue(), '')
        self.add_message('second outage')
        self.store.error = cloud.CloudError('synthetic upload outage')
        self.worker._tick()
        self.store.error = None
        self.clock.return_value += 5
        self.worker._tick()
        self.assertEqual(self.queue(), '')
        self.assertEqual(self.err.getvalue().count('同期が再開しました'), 2)
        self.assertEqual(self.err.getvalue().count('!'), 2)

    def test_errors_never_expose_response_details_in_alerts(self):
        self.http.return_value = 400, b'{"error":"invalid_grant","error_description":"synthetic-private-detail"}'
        self.worker.start()
        self.add_message()
        self.worker._tick()
        self.assertIn('watari auth', self.err.getvalue())
        self.assertNotIn('synthetic-private-detail', self.err.getvalue())
        self.assertNotIn('synthetic-refresh', self.err.getvalue())

    def test_fully_unconfigured_start_never_connects_or_queues(self):
        config.save_config(google={})
        self.worker.start()
        self.add_message()
        self.worker.stop_and_flush()
        self.assertFalse(self.worker._enabled)
        self.http.assert_not_called()
        self.get_store.assert_not_called()
        self.assertFalse(Path(relay._queue_path()).exists())
        self.assertEqual(self.err.getvalue(), '')

    def test_upload_failures_back_off_and_recovery_clears_warning(self):
        self.worker.start()
        self.add_message()
        self.store.error = cloud.CloudError('synthetic upload failure')
        with patch.object(self.store, 'append', wraps=self.store.append) as append:
            self.worker._tick()
            queued = self.queue()
            self.worker._tick()
            self.assertEqual(append.call_count, 1)
            self.assertNotIn('watari auth', self.err.getvalue())
            self.store.error = None
            self.clock.return_value += 5
            self.worker._tick()
            self.assertEqual(self.store.sent[0][1], queued)
            self.assertEqual(self.queue(), '')
            self.assertEqual(self.err.getvalue().count('同期が再開しました'), 1)
            self.add_message('later')
            self.store.error = cloud.OAuthTokenError('synthetic revocation', code='invalid_grant')
            self.worker._tick()
            self.assertIn('watari auth', self.err.getvalue())
            self.assertIn('later', self.queue())
            self.assertEqual(self.err.getvalue().count('!'), 2)

    def test_auth_error_after_network_error_is_not_suppressed(self):
        self.http.side_effect = cloud.CloudError('synthetic outage')
        self.worker.start()
        self.add_message()
        self.worker._tick()
        self.http.side_effect = None
        self.http.return_value = 400, b'{"error":"invalid_grant"}'
        self.clock.return_value += 600
        self.worker._tick()
        self.assertIn('watari auth', self.err.getvalue())
        self.assertEqual(self.err.getvalue().count('!'), 2)

    def test_large_queue_alone_must_not_request_reauthentication(self):
        Path(relay._queue_path()).write_text('synthetic pending\n')
        with patch.object(relay, 'QUEUE_WARN_BYTES', 1):
            self.worker.start()
        self.assertIn('たまっています', self.err.getvalue())
        self.assertNotIn('watari auth', self.err.getvalue())


if __name__ == '__main__':
    unittest.main()
