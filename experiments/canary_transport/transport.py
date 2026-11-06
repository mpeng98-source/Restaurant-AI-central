"""Loopback-only TLS acceptance harness. No production endpoint or live key input.

This tests transport controls, NOT provider compatibility or token pricing.
The count proof below is synthetic; the production admission gate remains absent.
"""
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import ssl
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'unattended_offline'))
from controller import Controller, Denied

MODEL = 'gpt-6-luna'
MAX_BODY = 32768
MAX_HEADERS = 8192
PIN = 'a' * 64


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def payload(prompt):
    if type(prompt) is not str or len(prompt.encode()) > 4096:
        raise Denied('bounded text input required')
    return encode(dict(model=MODEL, input=prompt, tools=[], tool_choice='none',
                       max_output_tokens=1024, reasoning={'effort': 'none'},
                       service_tier='default', stream=False, background=False,
                       store=False, truncation='disabled'))


def strict_json(body):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise Denied('duplicate JSON key')
            result[k] = v
        return result
    return json.loads(body, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(Denied('nonfinite JSON')))


def validate(body, counted):
    r = strict_json(body)
    if (type(r) is not dict or r.get('object') != 'response'
            or type(r.get('id')) is not str or not r['id'].startswith('resp_')
            or r.get('status') != 'completed' or r.get('model') != MODEL
            or r.get('service_tier') != 'default' or r.get('error') is not None
            or r.get('incomplete_details') is not None):
        raise Denied('response identity/status mismatch')
    u = r.get('usage')
    if type(u) is not dict or set(u) != {'input_tokens', 'output_tokens', 'total_tokens',
                                        'input_tokens_details', 'output_tokens_details'}:
        raise Denied('unknown usage contract')
    a, b, total = (u[k] for k in ('input_tokens', 'output_tokens', 'total_tokens'))
    if (any(type(x) is not int for x in (a, b, total)) or a != counted
            or not 0 <= b <= 1024 or total != a + b):
        raise Denied('usage exceeds admitted bounds')
    for field, key, bound in [('input_tokens_details', 'cached_tokens', a),
                              ('output_tokens_details', 'reasoning_tokens', b)]:
        d = u[field]
        if (type(d) is not dict or set(d) != {key} or type(d[key]) is not int
                or not 0 <= d[key] <= bound):
            raise Denied('unknown usage detail; no settlement')
    output = r.get('output')
    if type(output) is not list or len(output) != 1:
        raise Denied('one message required')
    item = output[0]
    if (type(item) is not dict or item.get('type') != 'message'
            or item.get('role') != 'assistant' or item.get('status') != 'completed'):
        raise Denied('tool or incomplete output')
    parts = item.get('content')
    if (type(parts) is not list or len(parts) != 1 or type(parts[0]) is not dict
            or parts[0].get('type') != 'output_text' or type(parts[0].get('text')) is not str
            or parts[0].get('annotations') != []):
        raise Denied('unsupported text output')
    return parts[0]['text']


class LoopbackTLS:
    """Fixed IP/SNI/key: cannot be configured to contact an external provider.

    Minimal HTTP/1.1 subset: Content-Length JSON only, no compression/chunking,
    redirects/proxy/DNS/retries. Strict subset may reject valid provider replies.
    """
    def __init__(self, port, cafile):
        if type(port) is not int or not 1024 <= port <= 65535:
            raise Denied('invalid fixture port')
        self.port = port
        self.context = ssl.create_default_context(cafile=str(cafile))
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2

    def send(self, body, timeout=1.0):
        if type(body) is not bytes or len(body) > 8192 or not 0 < timeout <= 5:
            raise Denied('transport bounds')
        deadline = time.monotonic() + timeout
        def remaining(sock):
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError('absolute transport deadline')
            sock.settimeout(left)
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            remaining(raw)
            raw.connect(('127.0.0.1', self.port))
            with self.context.wrap_socket(raw, server_hostname='fixture.invalid',
                                          do_handshake_on_connect=False) as s:
                remaining(s)
                s.do_handshake()
                request = (b'POST /v1/responses HTTP/1.1\r\nHost: fixture.invalid\r\n'
                           b'Authorization: Bearer synthetic-only\r\nContent-Type: application/json\r\n'
                           b'Accept-Encoding: identity\r\nConnection: close\r\nContent-Length: '
                           + str(len(body)).encode() + b'\r\n\r\n' + body)
                remaining(s)
                s.sendall(request)
                data = bytearray()
                while b'\r\n\r\n' not in data:
                    remaining(s)
                    chunk = s.recv(1)  # Header hard bound; no read-ahead ambiguity.
                    if not chunk:
                        raise Denied('truncated headers')
                    data.extend(chunk)
                    if len(data) > MAX_HEADERS:
                        raise Denied('header byte bound')
                lines = bytes(data[:-4]).split(b'\r\n')
                if lines[0] != b'HTTP/1.1 200 OK':
                    raise Denied('status rejected; no retry or redirect')
                headers = {}
                for line in lines[1:]:
                    name, value = line.split(b':', 1)
                    name = name.lower()
                    if name in headers or not name or name.strip() != name:
                        raise Denied('ambiguous headers')
                    headers[name] = value.strip()
                if (b'transfer-encoding' in headers or b'content-encoding' in headers
                        or headers.get(b'content-type') != b'application/json'):
                    raise Denied('unsupported HTTP framing')
                length = headers.get(b'content-length', b'')
                if not length.isdigit() or len(length) > 6 or not 0 < int(length) <= MAX_BODY:
                    raise Denied('body byte bound')
                data = bytearray()
                while len(data) < int(length):
                    remaining(s)
                    chunk = s.recv(min(4096, int(length)-len(data)))
                    if not chunk:
                        raise Denied('truncated body')
                    data.extend(chunk)
                remaining(s)
                return bytes(data)
        finally:
            raw.close()


class Canary:
    def __init__(self, controller, transport):
        if type(controller) is not Controller or type(transport) is not LoopbackTLS:
            raise Denied('fixture boundary required')
        self.c, self.transport = controller, transport
        self.c.db.execute('CREATE TABLE IF NOT EXISTS canary_once (id INTEGER PRIMARY KEY CHECK(id=1), digest TEXT NOT NULL)')

    def run(self, body, synthetic_count, digest, now=100, timeout=1.0):
        if (type(body) is not bytes or hashlib.sha256(body).hexdigest() != digest
                or type(synthetic_count) is not int or not 0 <= synthetic_count <= 4096):
            raise Denied('invalid synthetic count binding')
        parsed = strict_json(body)
        if type(parsed) is not dict or body != payload(parsed.get('input')):
            raise Denied('request differs from fixed canary contract')
        # This is NOT a provider-verifiable count or live financial admission proof.
        with self.c.transaction():
            try:
                self.c.db.execute('INSERT INTO canary_once VALUES(1,?)', (digest,))
            except sqlite3.IntegrityError:
                raise Denied('one-use canary already consumed') from None
        ticket = self.c.request_ticket('task', 1, now, runtime_digest=PIN)
        try:
            text = validate(self.transport.send(body, timeout), synthetic_count)
            self.c.record_response(ticket)
            self.c.complete('task', 1, now)
            return text
        except Exception:
            self.c.stop()
            raise Denied('uncertain request; exposure retained; stopped') from None
