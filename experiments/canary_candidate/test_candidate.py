import contextlib
import io
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import run
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'canary_transport'))
from test_transport import response


class Tests(unittest.TestCase):
    def test_fixed_request_excludes_tools_history_and_streaming(self):
        self.assertEqual(run.PAYLOAD['tools'], [])
        self.assertFalse(run.PAYLOAD['stream'])
        self.assertFalse(run.PAYLOAD['background'])
        self.assertEqual(run.PAYLOAD['max_output_tokens'], 1024)
        self.assertNotIn('previous_response_id',run.PAYLOAD)

    def test_response_and_real_worker_assertions(self):
        source,usage=run.validate(json.dumps(response()).encode())
        out=io.StringIO()
        with patch('sys.stdin',io.StringIO(json.dumps({'text':source}))), contextlib.redirect_stdout(out):
            exec(run.WORKER,{})
        self.assertEqual(json.loads(out.getvalue())['tests_passed'],2)

    def test_rejects_tool_code_or_usage_overrun(self):
        for key,value in [('model','other'),('service_tier','fast'),('status','incomplete')]:
            r=response();r[key]=value
            with self.assertRaises(ValueError):run.validate(json.dumps(r).encode())
        r=response();r['output'][0]['content'][0]['text']='import os'
        with self.assertRaises(ValueError):run.validate(json.dumps(r).encode())
        r=response();r['usage']['output_tokens']=1025
        with self.assertRaises(ValueError):run.validate(json.dumps(r).encode())

    def test_fixed_tls_host_one_request_and_no_retry(self):
        for status in (200,307,429,503):
            calls=[]
            class Connection:
                def __init__(self,*a,**kw):calls.append(('connect',a,kw))
                def request(self,*a,**kw):calls.append(('request',a,kw))
                def getresponse(self):return self
                def getheader(self,name):return None
                def read(self,n):return json.dumps(response()).encode()
                def close(self):pass
            Connection.status=status
            class Output:
                buffer=io.BytesIO()
            with patch('http.client.HTTPSConnection',Connection), patch('sys.stdin',io.StringIO('synthetic-only\n')), patch('sys.stdout',Output()), patch('sys.stderr',io.StringIO()):
                try:exec(run.BROKER,{'PAYLOAD_BYTES':b'{}','PROJECT':run.PROJECT})
                except SystemExit as e:self.assertEqual(e.code,2)
            self.assertEqual(calls[0][1],('api.openai.com',443))
            self.assertEqual(len([x for x in calls if x[0]=='request']),1)
            self.assertEqual(calls[1][1][:2],('POST','/v1/responses'))

    def test_outer_timeout_removes_broker_without_retry_or_secret_argv(self):
        with tempfile.TemporaryDirectory() as root:
            env={'GITHUB_REPOSITORY':'mpeng98-source/Restaurant-AI-central',
                 'GITHUB_WORKFLOW_REF':'mpeng98-source/Restaurant-AI-central/.github/workflows/chubby-dev-agent-gated.yml@refs/heads/main',
                 'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_REF':'refs/heads/main',
                 'GITHUB_RUN_ATTEMPT':'1','CANARY_MODE':'synthetic-one-shot-v1',
                 'PROJECT_ID':run.PROJECT,'RUNNER_TEMP':root,'GITHUB_RUN_ID':'42',
                 'OPENAI_API_KEY':'synthetic-test-key','GITHUB_SHA':'a'*40,'PATH':'/usr/bin'}
            calls=[]
            def child(argv,**kwargs):
                calls.append((argv,kwargs))
                self.assertNotIn('synthetic-test-key',str(argv))
                self.assertNotIn('OPENAI_API_KEY',kwargs['env'])
                if 'run' in argv:raise subprocess.TimeoutExpired(argv,20)
                return subprocess.CompletedProcess(argv,0,b'',b'')
            with patch.dict('os.environ',env,clear=True),patch('subprocess.run',child),patch('run.require_fresh_admission'):
                with self.assertRaises(subprocess.TimeoutExpired):run.main()
                self.assertTrue(Path(root,'scoped-canary-42').exists())
                with self.assertRaises(FileExistsError):run.main()
            self.assertEqual(sum('run' in a for a,k in calls),1)
            self.assertEqual(sum('rm' in a for a,k in calls),1)

    def test_real_receipt_expiry_and_runway_are_not_extended(self):
        from dataclasses import asdict
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
        from dev_agent_execution_gate import Context,digest_task
        ctx=Context('mpeng98-source/Restaurant-AI-central','.github/workflows/chubby-dev-agent-gated.yml',
                    'refs/heads/main','a'*40,42,1,99,run.PROJECT)
        task={'number':99,'title':'synthetic','body':'synthetic'}
        plan={'context':asdict(ctx),'task':task,'task_digest':digest_task(task)}
        receipt={'allowed':True,'context':asdict(ctx),'task_digest':plan['task_digest'],
                 'authorized_at':100,'admit_before':400}
        env={'PLAN_JSON':json.dumps(plan),'AUTHORIZATION_JSON':json.dumps(receipt),
             'GITHUB_REPOSITORY':ctx.repository,'GITHUB_REF':ctx.ref,'GITHUB_SHA':ctx.head_sha,
             'GITHUB_RUN_ID':'42','GITHUB_RUN_ATTEMPT':'1','REQUESTED_ISSUE':'99','PROJECT_ID':run.PROJECT}
        with patch.dict('os.environ',env,clear=True):
            run.require_fresh_admission(100);run.require_fresh_admission(370)
            for now in (99,371,400,999):
                with self.assertRaises(ValueError):run.require_fresh_admission(now)

    def test_preserved_usage_on_invalid_generated_code(self):
        with tempfile.TemporaryDirectory() as root:
            env={'GITHUB_REPOSITORY':'mpeng98-source/Restaurant-AI-central',
                 'GITHUB_WORKFLOW_REF':'mpeng98-source/Restaurant-AI-central/.github/workflows/chubby-dev-agent-gated.yml@refs/heads/main',
                 'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_REF':'refs/heads/main',
                 'GITHUB_RUN_ATTEMPT':'1','CANARY_MODE':'synthetic-one-shot-v1',
                 'PROJECT_ID':run.PROJECT,'RUNNER_TEMP':root,'GITHUB_RUN_ID':'42',
                 'OPENAI_API_KEY':'synthetic-test-key','GITHUB_SHA':'a'*40,'PATH':'/usr/bin'}
            r=response();r['output'][0]['content'][0]['text']='UNTRUSTED RAW CONTENT'
            def child(argv,**kwargs):
                return subprocess.CompletedProcess(argv,0,json.dumps(r).encode() if 'run' in argv else b'',b'')
            with patch.dict('os.environ',env,clear=True),patch('subprocess.run',child),patch('run.require_fresh_admission'):
                with self.assertRaises((ValueError,SyntaxError)):run.main()
            data=Path(root,'scoped-canary-result.json').read_text()
            record=json.loads(data)
            self.assertEqual(record['status'],'uncertain')
            self.assertEqual(record['usage']['input_tokens'],100)
            self.assertIn('response_sha256',record)
            self.assertNotIn('UNTRUSTED RAW CONTENT',data)
            self.assertNotIn('synthetic-test-key',data)

    def test_image_delay_expiry_prevents_provider_launch(self):
        with tempfile.TemporaryDirectory() as root:
            env={'GITHUB_REPOSITORY':'mpeng98-source/Restaurant-AI-central',
                 'GITHUB_WORKFLOW_REF':'mpeng98-source/Restaurant-AI-central/.github/workflows/chubby-dev-agent-gated.yml@refs/heads/main',
                 'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_REF':'refs/heads/main',
                 'GITHUB_RUN_ATTEMPT':'1','CANARY_MODE':'synthetic-one-shot-v1',
                 'PROJECT_ID':run.PROJECT,'RUNNER_TEMP':root,'GITHUB_RUN_ID':'42',
                 'OPENAI_API_KEY':'synthetic-test-key','GITHUB_SHA':'a'*40,'PATH':'/usr/bin'}
            with patch.dict('os.environ',env,clear=True),patch('subprocess.run') as child,patch('run.require_fresh_admission',side_effect=[None,ValueError('expired')]):
                with self.assertRaises(ValueError):run.main()
            self.assertEqual(child.call_count,1) # image inspect only
            record=json.loads(Path(root,'scoped-canary-result.json').read_text())
            self.assertEqual(record['status'],'not_dispatched')
            self.assertEqual(record['provider_calls'],0)

    def test_import_and_invalid_context_never_dispatch(self):
        with patch.dict('os.environ',{},clear=True), patch('subprocess.run') as child:
            with self.assertRaises(ValueError):run.main()
            child.assert_not_called()


if __name__=='__main__':unittest.main()
