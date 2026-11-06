import hashlib
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

from transport import Canary, Controller, Denied, LoopbackTLS, MODEL, PIN, encode, payload


def response():
    return {'id': 'resp_fixture', 'object': 'response', 'status': 'completed',
            'model': MODEL, 'service_tier': 'default', 'error': None, 'incomplete_details': None,
            'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': 'def add(a, b): return a + b', 'annotations': []}]}],
            'usage': {'input_tokens': 100, 'output_tokens': 10, 'total_tokens': 110,
                      'input_tokens_details': {'cached_tokens': 0},
                      'output_tokens_details': {'reasoning_tokens': 0}}}


class Provider:
    def __init__(self, cert, key, wire, mode='normal'):
        self.wire, self.mode, self.requests, self.connections = wire, mode, [], 0
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(cert, key)
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.port = self.listener.getsockname()[1]
        self.listener.listen()
        self.listener.settimeout(.05)
        self.done = threading.Event()
        self.thread = threading.Thread(target=self.serve)
        self.thread.start()

    def serve(self):
        while not self.done.is_set():
            try:
                raw, _ = self.listener.accept()
            except socket.timeout:
                continue
            self.connections += 1
            try:
                raw.settimeout(.5)
                if self.mode == 'handshake_stall':
                    self.done.wait(.4)
                    raw.close()
                    continue
                with self.context.wrap_socket(raw, server_side=True) as s:
                    data = b''
                    while b'\r\n\r\n' not in data:
                        data += s.recv(1)
                    length = int(data.split(b'Content-Length: ')[1].split(b'\r\n')[0])
                    body = b''
                    while len(body) < length:
                        body += s.recv(length-len(body))
                    self.requests.append((data, body))
                    if self.mode in ('slow', 'slow_body'):
                        tail = self.wire
                        if self.mode == 'slow_body':
                            head, tail = self.wire.split(b'\r\n\r\n', 1)
                            s.sendall(head+b'\r\n\r\n')
                        for byte in tail:
                            if self.done.wait(.02):
                                break
                            s.sendall(bytes([byte]))
                    elif self.mode == 'drop':
                        pass
                    else:
                        s.sendall(self.wire)
            except (OSError, ssl.SSLError):
                raw.close()

    def close(self):
        self.done.set()
        self.thread.join(2)
        self.listener.close()
        assert not self.thread.is_alive()


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = tempfile.TemporaryDirectory()
        root = Path(cls.keys.name)
        cls.cert, cls.key = root/'cert.pem', root/'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(cls.key), '-out', str(cls.cert), '-days', '1',
                        '-subj', '/CN=fixture.invalid', '-addext', 'subjectAltName=DNS:fixture.invalid'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @classmethod
    def tearDownClass(cls):
        cls.keys.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'ledger.db'
        self.c = Controller(self.path, runtime_digest=PIN)
        self.c.fixture_cost(100, 0)
        self.c.enqueue('task', 'b'*64)
        self.c.claim('task', 'b'*64, 100)
        self.providers = []
        self.body = payload('Fix synthetic add(a,b) that subtracts.')
        self.digest = hashlib.sha256(self.body).hexdigest()

    def tearDown(self):
        for p in self.providers:
            p.close()
        self.c.close()
        self.tmp.cleanup()

    def broker(self, body=None, status=b'200 OK', headers=b'', mode='normal', raw=None):
        body = encode(response()) if body is None else body
        wire = raw if raw is not None else (b'HTTP/1.1 '+status+b'\r\nContent-Type: application/json\r\nContent-Length: '
                                             +str(len(body)).encode()+b'\r\n'+headers+b'\r\n'+body)
        p = Provider(self.cert, self.key, wire, mode)
        self.providers.append(p)
        return Canary(self.c, LoopbackTLS(p.port, self.cert)), p

    def run_canary(self, b, timeout=1):
        return b.run(self.body, 100, self.digest, timeout=timeout)

    def retained(self):
        self.assertEqual(self.c.db.execute('SELECT reserve FROM jobs').fetchone()[0], 2_000_000)

    def test_success_exact_wire_and_no_second_request_after_reopen(self):
        b, p = self.broker()
        self.assertIn('a + b', self.run_canary(b))
        self.assertEqual(p.requests[0][1], self.body)
        self.assertIn(b'Bearer synthetic-only', p.requests[0][0])
        self.c.close()
        self.c = Controller(self.path, runtime_digest=PIN)
        reopened = Canary(self.c, b.transport)
        with self.assertRaises(Denied):
            self.run_canary(reopened)
        self.assertEqual(len(p.requests), 1)
        self.assertEqual(self.c.db.execute('SELECT state FROM jobs').fetchone()[0], 'awaiting_review')
        self.retained()

    def test_redirect_and_rate_server_errors_never_retry(self):
        for status in (b'307 Temporary Redirect', b'429 Too Many Requests', b'503 Unavailable'):
            with self.subTest(status=status):
                b, p = self.broker(status=status, headers=b'Location: https://api.openai.com/v1/responses\r\n')
                with self.assertRaises(Denied):
                    b.transport.send(self.body)
                self.assertEqual(p.connections, 1)
        b, p = self.broker(status=b'307 Temporary Redirect')
        with self.assertRaises(Denied):
            self.run_canary(b)
        with self.assertRaises(Denied):
            self.run_canary(b)
        self.assertEqual(p.connections, 1)
        self.retained()

    def test_partial_body_stays_pending_after_reopen(self):
        b, p = self.broker(raw=b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{')
        with self.assertRaises(Denied):
            self.run_canary(b)
        self.c.close()
        self.c = Controller(self.path, runtime_digest=PIN)
        self.assertEqual(self.c.db.execute('SELECT state FROM requests').fetchone()[0], 'pending')
        with self.assertRaises(Denied):
            self.run_canary(Canary(self.c, b.transport))
        self.assertEqual(len(p.requests), 1)
        self.retained()

    def test_slow_headers_obey_absolute_deadline(self):
        b, p = self.broker(mode='slow')
        start = time.monotonic()
        with self.assertRaises(Denied):
            self.run_canary(b, .15)
        self.assertLess(time.monotonic()-start, .5)
        self.assertEqual(len(p.requests), 1)
        self.retained()

    def test_body_drip_cannot_extend_total_deadline(self):
        b, p = self.broker(mode='slow_body')
        start = time.monotonic()
        with self.assertRaises(Denied): self.run_canary(b, .15)
        self.assertLess(time.monotonic()-start, .5)
        self.assertEqual(len(p.requests), 1)
        self.assertEqual(self.c.db.execute('SELECT state FROM requests').fetchone()[0], 'pending')
        self.retained()

    def test_tls_handshake_stall_is_bounded_without_http_retry(self):
        b, p = self.broker(mode='handshake_stall')
        start = time.monotonic()
        with self.assertRaises(Denied): self.run_canary(b, .15)
        self.assertLess(time.monotonic()-start, .5)
        self.assertEqual(p.connections, 1)
        self.assertEqual(p.requests, [])
        self.retained()

    def test_untrusted_tls_certificate_sends_no_request(self):
        b, p = self.broker()
        b.transport.context = ssl.create_default_context()
        with self.assertRaises(Denied):
            self.run_canary(b)
        self.assertEqual(p.requests, [])
        self.retained()

    def test_stopped_and_digest_mismatch_send_nothing(self):
        b, p = self.broker()
        with self.assertRaises(Denied):
            b.run(self.body, 100, '0'*64)
        self.c.stop()
        with self.assertRaises(Denied):
            self.run_canary(b)
        self.assertEqual(p.connections, 0)

    def test_malformed_json_and_usage_contracts(self):
        from transport import validate
        cases = [b'{', b'{"id":1,"id":2}', b'{"x":NaN}']
        for key, value in [('model', 'other'), ('status', 'incomplete'), ('service_tier', 'fast'),
                           ('output', [{'type': 'function_call'}])]:
            r = response(); r[key] = value; cases.append(encode(r))
        for key, value in [('input_tokens', 101), ('output_tokens', 1025), ('total_tokens', True),
                           ('input_tokens_details', {'cached_tokens': 0, 'unknown_charge': 1})]:
            r = response(); r['usage'][key] = value; cases.append(encode(r))
        for body in cases:
            with self.subTest(body=body), self.assertRaises((Denied, ValueError)):
                validate(body, 100)

    def test_invalid_usage_latches_stop(self):
        r = response(); r['usage']['output_tokens'] = 1025
        b, p = self.broker(body=encode(r))
        with self.assertRaises(Denied):
            self.run_canary(b)
        self.assertEqual(self.c.db.execute('SELECT stopped FROM control').fetchone()[0], 1)
        self.assertEqual(self.c.db.execute('SELECT state FROM requests').fetchone()[0], 'pending')
        self.retained()

    def test_request_overrides_rejected_before_network(self):
        import json
        b, p = self.broker()
        for key, value in [('tools', [{'type': 'web_search'}]), ('model', 'other'),
                           ('max_output_tokens', 999999), ('stream', True),
                           ('previous_response_id', 'resp_remote')]:
            body = json.loads(self.body); body[key] = value; body = encode(body)
            with self.subTest(key=key), self.assertRaises(Denied):
                b.run(body, 100, hashlib.sha256(body).hexdigest())
        self.assertEqual(p.connections, 0)

    def test_crash_after_one_use_commit_cannot_replay(self):
        b, p = self.broker()
        # Simulate termination in the conservative gap before ticket creation.
        with self.c.transaction():
            self.c.db.execute('INSERT INTO canary_once VALUES(1,?)', (self.digest,))
        self.c.close()
        self.c = Controller(self.path, runtime_digest=PIN)
        with self.assertRaises(Denied):
            self.run_canary(Canary(self.c, b.transport))
        self.assertEqual(p.connections, 0)
        self.retained()

    def test_http_framing_bounds(self):
        # Independent transport calls to separate fake endpoints; no paid path.
        cases = [b'Content-Length: 1\r\n', b'Transfer-Encoding: chunked\r\n',
                 b'Content-Encoding: gzip\r\n', b'X-Fill: '+b'x'*8192+b'\r\n']
        for extra in cases:
            b, p = self.broker(headers=extra)
            with self.subTest(extra=extra[:30]), self.assertRaises(Denied):
                b.transport.send(self.body)
            self.assertEqual(len(p.requests), 1)
        for length in (b'999999', b'-1'):
            b, p = self.broker(raw=b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+length+b'\r\n\r\n')
            with self.assertRaises(Denied):
                b.transport.send(self.body)


if __name__ == '__main__':
    unittest.main()
