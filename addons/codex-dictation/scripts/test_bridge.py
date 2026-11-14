"""HTTP trust boundary and isolated-session ownership. No credentials or network services."""
import json
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
import sys
import io
sys.dont_write_bytecode = True
import os
import stat
import tempfile
from pathlib import Path
from bridge import Bridge, CodexSession, ProtocolError, probe


class FakeSession:
    def __init__(self, _codex):
        self.closed = False
    def renew(self):
        if self.closed:
            raise ValueError("Session ended.")
    def start(self, sdp):
        return 'v=0\r\nanswer'
    def close(self):
        self.closed = True


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.server = Bridge('unused', 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.close_sessions)
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def post(self, path, body, origin='t3code://app', custom=True):
        headers = {'Content-Type': 'application/json', 'Origin': origin}
        if custom:
            headers['X-T3-Dictation'] = '1'
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(), headers=headers)
        return json.load(urllib.request.urlopen(req))

    def test_arbitrary_websites_null_origins_and_simple_requests_are_rejected(self):
        for origin in ['https://example.com', 'null', 'http://127.0.0.1:9999']:
            with self.assertRaises(urllib.error.HTTPError) as e:
                self.post('/health', {}, origin)
            self.assertEqual(e.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError):
            self.post('/health', {}, custom=False)

    @patch('bridge.CodexSession', FakeSession)
    def test_only_one_session_can_run_and_stop_is_idempotent(self):
        first = self.post('/start', {'sdp': 'v=0\r\noffer'})
        self.assertEqual(first['sdp'], 'v=0\r\nanswer')
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post('/start', {'sdp': 'v=0\r\noffer'})
        self.assertEqual(e.exception.code, 400)
        self.assertEqual(self.post('/keepalive', {'id': first['id']}), {})
        self.assertEqual(self.post('/stop', {'id': first['id']}), {})
        self.assertEqual(self.post('/stop', {'id': first['id']}), {})
        self.assertIn('id', self.post('/start', {'sdp': 'v=0\r\nnew'}))

    def test_invalid_sdp_never_starts_codex(self):
        with patch('bridge.CodexSession') as session:
            with self.assertRaises(urllib.error.HTTPError):
                self.post('/start', {'sdp': 'not an offer'})
            session.assert_not_called()

    def test_unexpected_agent_turn_terminates_the_isolated_process(self):
        session = CodexSession('unused')
        session.proc = type('Process', (), {'pid': 12345, 'poll': lambda self: 0, 'stdout': io.StringIO('{"method":"turn/started","params":{}}\n')})()
        with patch('bridge.os.killpg') as kill:
            session.read()
        kill.assert_called_once()
        self.assertIn('Unexpected agent turn', session.events.get()['params']['message'])


    def test_live_client_renewals_keep_recording_but_abandoned_sessions_expire(self):
        session = CodexSession('unused')
        with patch('bridge.threading.Timer') as timer:
            session.renew()
            first_generation = session.lease_generation
            session.renew()
            timer.return_value.cancel.assert_called_once()
            session.expire(first_generation)
            self.assertFalse(session.closed, 'An old timeout cannot close a renewed session')
            session.expire(session.lease_generation)
            self.assertTrue(session.closed)
            with self.assertRaises(ValueError):
                session.renew()

    def test_process_exit_marks_session_closed_so_new_recordings_are_not_blocked(self):
        session = CodexSession('unused')
        session.proc = type('Process', (), {'stdout': io.StringIO(''), 'poll': lambda self: 0})()
        session.read()
        self.assertTrue(session.closed)


FAKE = """#!{python}
import json, sys
mode = {mode!r}
if '--version' in sys.argv:
    print('codex-cli ' + {version!r}); sys.exit(0)
for line in sys.stdin:
    msg = json.loads(line)
    method, ident = msg.get('method'), msg.get('id')
    if ident is None:
        continue
    def reply(result=None, error=None):
        print(json.dumps({{'id': ident, **({{'error': error}} if error else {{'result': result}})}}), flush=True)
    if method == 'initialize':
        if mode == 'hang':
            continue
        if mode == 'die':
            sys.exit(3)
        reply({{'userAgent': 'fake'}}) if mode != 'no-handshake' else reply(error={{'code': -32601, 'message': 'Method not found'}})
    elif method == 'account/read':
        reply({{'account': None}} if mode != 'bad-shape' else {{'unexpected': True}})
    elif method == 'thread/start' and mode == 'start-missing':
        reply(error={{'code': -32601, 'message': 'Method not found'}})
    elif method == 'thread/start' and mode == 'start-rejected':
        reply(error={{'code': -32602, 'message': 'Invalid params'}})
    elif method == 'thread/realtime/start' and mode == 'missing-method':
        reply(error={{'code': -32601, 'message': 'Method not found'}})
    else:
        reply(error={{'code': -32602, 'message': 'Invalid params'}})
"""


class ProbeTests(unittest.TestCase):
    def fake(self, version, mode='ok'):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'codex'
        path.write_text(FAKE.format(python=sys.executable, mode=mode, version=version))
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return str(path)

    def test_any_codex_version_with_the_needed_protocol_is_accepted(self):
        for version in ('0.167.0', '0.169.0', '0.200.1'):
            self.assertEqual(probe(self.fake(version)), 'codex-cli ' + version)

    def test_real_protocol_mismatches_are_refused_clearly(self):
        for mode, text in (('no-handshake', 'does not provide initialize'), ('bad-shape', 'unexpected shape'),
                           ('missing-method', 'thread/realtime/start')):
            with self.subTest(mode):
                with self.assertRaisesRegex(ProtocolError, text):
                    probe(self.fake('0.169.0', mode))

    def test_method_not_found_for_thread_start_is_a_protocol_error(self):
        with self.assertRaisesRegex(ProtocolError, 'thread/start'):
            probe(self.fake('0.169.0', 'start-missing'))

    def test_thread_start_rejecting_the_invalid_probe_params_means_the_method_exists(self):
        self.assertEqual(probe(self.fake('0.169.0', 'start-rejected')), 'codex-cli 0.169.0')

    def test_hung_codex_times_out_as_an_ordinary_failure_not_a_protocol_error(self):
        with self.assertRaises(ValueError) as caught:
            probe(self.fake('0.169.0', 'hang'), timeout=0.5)
        self.assertNotIsInstance(caught.exception, ProtocolError)
        self.assertIn('did not respond in time', str(caught.exception))

    def test_process_dying_mid_probe_fails_promptly_and_is_not_a_protocol_error(self):
        import time
        started = time.monotonic()
        with self.assertRaises(ValueError) as caught:
            probe(self.fake('0.169.0', 'die'), timeout=20)
        self.assertNotIsInstance(caught.exception, ProtocolError)
        self.assertLess(time.monotonic() - started, 10)

    def test_close_survives_an_already_gone_process_group(self):
        session = CodexSession('unused')
        session.proc = type('P', (), {'pid': 1, 'poll': lambda self: None, 'wait': lambda self, timeout=None: None})()
        with patch('bridge.os.killpg', side_effect=ProcessLookupError):
            session.close()
        self.assertTrue(session.closed)


if __name__ == '__main__':
    unittest.main()
