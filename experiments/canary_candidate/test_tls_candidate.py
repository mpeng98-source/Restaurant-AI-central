"""Actual candidate BROKER + real stdlib HTTPS over loopback TLS; never external IO."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import run
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'canary_transport'))
from test_transport import Provider,response


class TLSCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();root=Path(cls.temp.name)
        cls.cert,cls.key=root/'cert.pem',root/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(cls.key),
                        '-out',str(cls.cert),'-days','1','-subj','/CN=api.openai.com',
                        '-addext','subjectAltName=DNS:api.openai.com'],check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def call(self,status=200,body=None,extra=b'',trusted=True,mode='normal',wire=None):
        body=json.dumps(response()).encode() if body is None else body
        wire=wire if wire is not None else (b'HTTP/1.1 '+str(status).encode()+b' TEST\r\nContent-Type: application/json\r\nContent-Length: '+str(len(body)).encode()+b'\r\n'+extra+b'\r\n'+body)
        p=Provider(self.cert,self.key,wire,mode)
        # Only socket destination and trust roots are fixture-controlled. The
        # candidate HTTPSConnection, HTTP parser, request headers, TLS/SNI and
        # BROKER bytes are unchanged. No mock HTTPS or provider response object.
        shim=f'''import socket,ssl
original_connect=socket.create_connection
original_context=ssl.create_default_context
def fixture_connect(address,*a,**kw):
 if address != ('api.openai.com',443): raise ValueError('unexpected destination')
 return original_connect(('127.0.0.1',{p.port}),*a,**kw)
socket.create_connection=fixture_connect
'''
        if trusted:shim+=f"ssl.create_default_context=lambda:original_context(cafile={str(self.cert)!r})\n"
        code=shim+'PROJECT='+repr(run.PROJECT)+'\nPAYLOAD_BYTES='+repr(json.dumps(run.PAYLOAD).encode())+'\n'+run.BROKER
        try:
            try:
                result=subprocess.run([sys.executable,'-I','-c',code],input=b'synthetic-only\n',capture_output=True,timeout=1)
            except subprocess.TimeoutExpired:
                result=None
            return result,list(p.requests),p.connections
        finally:p.close()

    def test_real_https_success_and_exact_request(self):
        result,requests,connections=self.call()
        self.assertEqual(result.returncode,0)
        self.assertEqual(connections,1)
        self.assertEqual(json.loads(requests[0][1]),run.PAYLOAD)
        self.assertIn(b'Host: api.openai.com',requests[0][0])
        self.assertIn(b'OpenAI-Project: '+run.PROJECT.encode(),requests[0][0])
        self.assertIn('return a + b',run.validate(result.stdout)[0])

    def test_redirect_and_errors_never_reconnect(self):
        for status in (307,429,503):
            result,requests,connections=self.call(status=status,extra=b'Location: https://example.invalid/\r\n')
            self.assertEqual(result.returncode,2)
            self.assertEqual(len(requests),1)
            self.assertEqual(connections,1)

    def test_real_tls_verification_rejects_untrusted_certificate(self):
        result,requests,connections=self.call(trusted=False)
        self.assertEqual(result.returncode,2);self.assertEqual(requests,[])

    def test_oversized_and_compressed_bodies_rejected(self):
        for body,extra in ((b'x'*32769,b''),(b'{}',b'Content-Encoding: gzip\r\n')):
            result,requests,connections=self.call(body=body,extra=extra)
            self.assertEqual(result.returncode,2);self.assertEqual(connections,1)

    def test_truncated_reply_never_passes_validation(self):
        result,requests,_=self.call(wire=b'HTTP/1.1 200 OK\r\nContent-Length: 999\r\n\r\n{')
        if result.returncode==0:
            with self.assertRaises((ValueError,KeyError)):run.validate(result.stdout)
        self.assertEqual(len(requests),1)

    def test_real_http_chunked_response(self):
        body=json.dumps(response()).encode()
        wire=b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n'+hex(len(body))[2:].encode()+b'\r\n'+body+b'\r\n0\r\n\r\n'
        result,requests,_=self.call(wire=wire)
        self.assertEqual(result.returncode,0);run.validate(result.stdout)
        self.assertEqual(len(requests),1)

    def test_slow_body_hits_external_watchdog(self):
        result,requests,connections=self.call(mode='slow_body')
        self.assertIsNone(result);self.assertEqual(len(requests),1);self.assertEqual(connections,1)


if __name__=='__main__':unittest.main()
