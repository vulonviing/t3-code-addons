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
from bridge import Bridge, CodexSession


class FakeSession:
    def __init__(self, _codex):
        self.closed = False
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
        session.proc = type('Process', (), {'pid': 12345, 'stdout': io.StringIO('{"method":"turn/started","params":{}}\n')})()
        with patch('bridge.os.killpg') as kill:
            session.read()
        kill.assert_called_once()
        self.assertIn('Unexpected agent turn', session.events.get()['params']['message'])


if __name__ == '__main__':
    unittest.main()
