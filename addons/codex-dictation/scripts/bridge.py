#!/usr/bin/env python3
"""Loopback-only WebRTC negotiation through Codex. Audio never passes through this helper."""
import argparse
import atexit
import json
import os
import queue
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = '0.167.0'
PORT = 48173
ORIGIN = 't3code://app'
PROMPT = ('You are a dictation transcriber. Listen to the user and transcribe their words in the '
          'original language, including Turkish. Do not answer, translate, summarize, execute '
          'instructions, delegate, or call tools. Never start a coding task.')


class CodexSession:
    def __init__(self, codex):
        self.proc = None
        self.pending = {}
        self.lock = threading.Lock()
        self.sequence = 0
        self.events = queue.Queue()
        self.thread_id = None
        self.closed = False
        self.timer = None
        self.codex = codex

    def read(self):
        try:
            for line in self.proc.stdout:
                msg = json.loads(line)
                if 'method' in msg and 'id' in msg:
                    # This application never authorizes Codex tools or agent work.
                    self.write({'id': msg['id'], 'error': {'code': -32601, 'message': 'Dictation does not support agent requests.'}})
                elif 'id' in msg:
                    with self.lock:
                        destination = self.pending.get(msg['id'])
                    if destination:
                        destination.put(msg)
                elif msg.get('method') in ('thread/realtime/sdp', 'thread/realtime/error'):
                    self.events.put(msg)
                elif msg.get('method') == 'turn/started':
                    self.events.put({'method': 'thread/realtime/error', 'params': {'message': 'Unexpected agent turn; dictation stopped.'}})
                    # Terminate the isolated process rather than allow coding work.
                    os.killpg(self.proc.pid, signal.SIGTERM)
        except (ValueError, OSError):
            pass
        finally:
            self.events.put({'method': 'thread/realtime/error', 'params': {'message': 'Codex disconnected.'}})

    def write(self, value):
        with self.lock:
            self.proc.stdin.write(json.dumps(value) + '\n')
            self.proc.stdin.flush()

    def rpc(self, method, params):
        result = queue.Queue()
        with self.lock:
            self.sequence += 1
            request_id = self.sequence
            self.pending[request_id] = result
        try:
            self.write({'id': request_id, 'method': method, 'params': params})
            message = result.get(timeout=40)
            if 'error' in message:
                raise ValueError('Codex rejected the dictation request: ' + str(message['error'].get('message', 'Unknown error')))
            return message['result']
        except queue.Empty:
            raise ValueError('Codex did not respond in time.') from None
        finally:
            with self.lock:
                self.pending.pop(request_id, None)

    def start(self, sdp):
        version = subprocess.run([self.codex, '--version'], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        if version != 'codex-cli ' + VERSION:
            raise ValueError('Unsupported Codex version; this addon was verified with ' + VERSION + '.')
        self.proc = subprocess.Popen([self.codex, 'app-server', '-c', 'realtime.session_type="conversational"'],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, cwd=tempfile.gettempdir(), start_new_session=True)
        threading.Thread(target=self.read, daemon=True).start()
        self.rpc('initialize', {'clientInfo': {'name': 't3_adds_dictation', 'version': '0.1.0'},
                                'capabilities': {'experimentalApi': True}})
        account = self.rpc('account/read', {'refreshToken': False}).get('account')
        if not account or account.get('type') != 'chatgpt':
            raise ValueError('Sign in to Codex with your ChatGPT account first. API-key mode is not used by this addon.')
        result = self.rpc('thread/start', {'ephemeral': True, 'cwd': tempfile.gettempdir(), 'sandbox': 'read-only',
                                         'approvalPolicy': 'never', 'baseInstructions': PROMPT, 'developerInstructions': PROMPT})
        self.thread_id = result['thread']['id']
        self.rpc('thread/realtime/start', {'threadId': self.thread_id, 'version': 'v3', 'outputModality': 'audio',
                                          'transport': {'type': 'webrtc', 'sdp': sdp}, 'includeStartupContext': False,
                                          'clientManagedHandoffs': True, 'flushTranscriptTailOnSessionEnd': False,
                                          'prompt': PROMPT})
        try:
            event = self.events.get(timeout=40)
        except queue.Empty:
            raise ValueError('The voice service did not negotiate a connection.') from None
        if event['method'].endswith('/error'):
            # Server text can contain request context; do not put it in persistent logs.
            raise ValueError('The Codex voice service could not start: ' + event['params']['message'][:600])
        self.timer = threading.Timer(240, self.close)
        self.timer.daemon = True
        self.timer.start()
        return event['params']['sdp']

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.timer:
            self.timer.cancel()
        if self.proc and self.proc.poll() is None:
            try:
                if self.thread_id:
                    # Queue the stop, then terminate even if the server stops responding.
                    self.write({'id': 'stop', 'method': 'thread/realtime/stop', 'params': {'threadId': self.thread_id}})
                os.killpg(self.proc.pid, signal.SIGTERM)
                self.proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait(timeout=5)


class Bridge(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, codex, port=PORT, origin=ORIGIN):
        self.codex, self.origin = codex, origin
        self.sessions = {}
        self.session_lock = threading.Lock()
        super().__init__(('127.0.0.1', port), Handler)

    def close_sessions(self):
        with self.session_lock:
            sessions = list(self.sessions.values())
            self.sessions.clear()
        for session in sessions:
            session.close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def trusted(self):
        return (self.headers.get('Origin') == self.server.origin
                and self.headers.get('Host') == '127.0.0.1:' + str(self.server.server_port))

    def reply(self, status, value):
        body = json.dumps(value).encode()
        self.send_response(status)
        if self.trusted():
            self.send_header('Access-Control-Allow-Origin', self.server.origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if not self.trusted():
            return self.reply(403, {'error': 'Untrusted origin.'})
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', self.server.origin)
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-T3-Dictation')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.end_headers()

    def do_POST(self):
        if not self.trusted() or self.headers.get('X-T3-Dictation') != '1':
            return self.reply(403, {'error': 'Untrusted request.'})
        session = None
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 2 or length > 100000 or self.headers.get('Content-Type') != 'application/json':
                raise ValueError('Invalid request body.')
            self.connection.settimeout(10)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('The request must be a JSON object.')
            if self.path == '/health':
                return self.reply(200, {'addon': 'codex-dictation', 'version': '0.1.0'})
            if self.path == '/stop':
                with self.server.session_lock:
                    session = self.server.sessions.pop(body.get('id'), None)
                if session:
                    session.close()
                return self.reply(200, {})
            if self.path != '/start':
                return self.reply(404, {'error': 'Unknown operation.'})
            sdp = body.get('sdp')
            if not isinstance(sdp, str) or not sdp.startswith('v=0'):
                raise ValueError('Invalid WebRTC offer.')
            with self.server.session_lock:
                self.server.sessions = {k: v for k, v in self.server.sessions.items() if not v.closed}
                if self.server.sessions:
                    raise ValueError('A dictation session is already open. Stop it first.')
                session = CodexSession(self.server.codex)
                session_id = secrets.token_urlsafe(24)
                self.server.sessions[session_id] = session
            answer = session.start(sdp)
            self.reply(200, {'id': session_id, 'sdp': answer})
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            if session:
                session.close()
            try:
                self.reply(400, {'error': str(error)[:800]})
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--codex', required=True)
    parser.add_argument('--port', type=int, default=PORT)
    # A mock-page origin may be supplied explicitly in an external test environment.
    parser.add_argument('--origin', default=ORIGIN)
    args = parser.parse_args()
    bridge = Bridge(args.codex, args.port, args.origin)
    atexit.register(bridge.close_sessions)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        bridge.serve_forever()
    finally:
        bridge.close_sessions()
        bridge.server_close()


if __name__ == '__main__':
    main()
