"""Review-only one-shot canary candidate. Not referenced by an active workflow.

Live invocation requires the separately reviewed workflow patch and its existing
protected admission. This module is safe to import; main alone performs IO.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import time

IMAGE = 'python@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54'
PROJECT = 'proj_Nkd1G85QX72VHwdQ8mEg8CRa'
MODEL = 'gpt-6-luna'
PROMPT = 'Return only this corrected Python function, without markdown: def add(a, b): return a - b. It must add the two numbers.'
PAYLOAD = {'model': MODEL, 'input': PROMPT, 'tools': [], 'tool_choice': 'none',
           'max_output_tokens': 1024, 'reasoning': {'effort': 'none'},
           'service_tier': 'default', 'stream': False, 'background': False,
           'store': False, 'truncation': 'disabled'}

# Trusted broker receives the existing secret over stdin, never via Docker argv,
# environment, a filesystem mount, or model-controlled input. Fixed host/path only.
BROKER = '''import http.client,json,ssl,sys,time
try:
 key=sys.stdin.readline().rstrip("\\n")
 if not key or len(key)>4096 or any(ord(c)<33 or ord(c)>126 for c in key): raise ValueError()
 body=PAYLOAD_BYTES
 conn=http.client.HTTPSConnection("api.openai.com",443,timeout=10,context=ssl.create_default_context())
 conn.request("POST","/v1/responses",body=body,headers={"Authorization":"Bearer "+key,"OpenAI-Project":PROJECT,"Content-Type":"application/json","Accept-Encoding":"identity","Connection":"close"})
 response=conn.getresponse()
 if response.status!=200: raise ValueError()
 if response.getheader("Content-Encoding") not in (None,"identity"): raise ValueError()
 raw=response.read(32769)
 if len(raw)>32768: raise ValueError()
 conn.close()
 # Return JSON bytes only to trusted host validator; not to worker directly.
 sys.stdout.buffer.write(raw)
except BaseException:
 sys.stderr.write("Canary provider result uncertain; no retry\\n")
 sys.exit(2)
'''
WORKER = '''import ast,json,sys
s=json.loads(sys.stdin.read(4096))["text"]
expected=ast.dump(ast.parse("def add(a, b): return a + b"),include_attributes=False)
assert ast.dump(ast.parse(s),include_attributes=False)==expected
scope={"__builtins__":{}}
exec(compile(s,"<synthetic>","exec"),scope)
assert scope["add"](2,3)==5 and scope["add"](-2,1)==-1
print('{"tests_passed":2,"publication":"none"}')
'''


def validate(raw):
    def pairs(items):
        out = {}
        for k,v in items:
            if k in out: raise ValueError('duplicate field')
            out[k] = v
        return out
    r = json.loads(raw, object_pairs_hook=pairs,
                   parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
    if (r.get('object') != 'response' or r.get('status') != 'completed'
            or r.get('model') != MODEL or r.get('service_tier') != 'default'
            or r.get('error') is not None or r.get('incomplete_details') is not None):
        raise ValueError('unexpected response')
    u = r['usage']
    for k in ('input_tokens','output_tokens','total_tokens'):
        if type(u[k]) is not int or u[k] < 0: raise ValueError('invalid usage')
    if u['input_tokens']>4096 or u['output_tokens']>1024 or u['total_tokens']!=u['input_tokens']+u['output_tokens']:
        raise ValueError('usage outside expected allowance')
    if len(r['output']) != 1: raise ValueError('unexpected output')
    msg = r['output'][0]
    if msg['type']!='message' or msg['role']!='assistant' or msg['status']!='completed': raise ValueError('tool or incomplete')
    if len(msg['content']) != 1: raise ValueError('unexpected content')
    part=msg['content'][0]
    if part['type']!='output_text' or part.get('annotations')!=[]: raise ValueError('nontext')
    text=part['text']
    if type(text) is not str or len(text.encode())>2048: raise ValueError('oversized text')
    if ast.dump(ast.parse(text),include_attributes=False)!=ast.dump(ast.parse('def add(a, b): return a + b'),include_attributes=False):
        raise ValueError('unexpected code')
    # Usage is evidence only, never settlement or an automatic refund.
    return text, u



def require_fresh_admission(now=None):
    # Reuse the existing receipt validator; do not renew, extend, or forge a receipt.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
    from dev_agent_execution_gate import Context, admit
    plan=json.loads(os.environ['PLAN_JSON'])
    receipt=json.loads(os.environ['AUTHORIZATION_JSON'])
    ctx=Context(os.environ['GITHUB_REPOSITORY'], '.github/workflows/chubby-dev-agent-gated.yml',
                os.environ['GITHUB_REF'], os.environ['GITHUB_SHA'],
                int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT']),
                int(os.environ['REQUESTED_ISSUE']), os.environ['PROJECT_ID'])
    now=int(time.time()) if now is None else now
    admit(receipt,plan,ctx=ctx,now=now)
    if receipt['admit_before']-now<30: raise ValueError('less than 30 seconds admission runway')


def save_evidence(record):
    target=Path(os.environ['RUNNER_TEMP'])/'scoped-canary-result.json'
    temporary=target.with_suffix('.tmp')
    temporary.write_text(json.dumps(record,sort_keys=True))
    temporary.chmod(0o600)
    temporary.replace(target)


def safe_usage(raw):
    # Preserve bounded numeric usage on code/test failure without storing raw replies.
    try:
        r=json.loads(raw); u=r['usage']
        keys=('input_tokens','output_tokens','total_tokens')
        if not all(type(u[k]) is int and 0<=u[k]<=10**9 for k in keys): return None
        return {k:u[k] for k in keys}
    except (ValueError,KeyError,TypeError): return None


def main():
    if (os.environ.get('GITHUB_REPOSITORY')!='mpeng98-source/Restaurant-AI-central'
            or os.environ.get('GITHUB_WORKFLOW_REF')!='mpeng98-source/Restaurant-AI-central/.github/workflows/chubby-dev-agent-gated.yml@refs/heads/main'
            or os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch'
            or os.environ.get('GITHUB_REF')!='refs/heads/main'
            or os.environ.get('GITHUB_RUN_ATTEMPT')!='1'
            or os.environ.get('CANARY_MODE')!='synthetic-one-shot-v1'
            or os.environ.get('PROJECT_ID')!=PROJECT):
        raise ValueError('wrong protected run context')
    require_fresh_admission()
    # Existing gate's signed permit has already been consumed by the immediately
    # preceding admission step. This local guard also refuses repeated invocations.
    marker=Path(os.environ['RUNNER_TEMP'])/('scoped-canary-'+os.environ['GITHUB_RUN_ID'])
    with marker.open('x') as f: f.write('pending; no refund or retry\n')
    record={'status':'pending','provider_calls':0,'budget_settled':False,
            'run_id':os.environ['GITHUB_RUN_ID'],'head_sha':os.environ['GITHUB_SHA'],
            'model':MODEL,'project':PROJECT,'payload_sha256':hashlib.sha256(json.dumps(PAYLOAD,separators=(',',':')).encode()).hexdigest()}
    save_evidence(record)
    secret=os.environ['OPENAI_API_KEY']
    if '\n' in secret or '\r' in secret: raise ValueError('invalid credential framing')
    docker=['docker','--host=unix:///var/run/docker.sock']
    env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','DOCKER_CONFIG')}
    common=['--pull=never','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges',
            '--user=65534:65534','--memory=256m','--cpus=1','--pids-limit=64',
            '--tmpfs=/tmp:rw,nosuid,nodev,size=32m','--log-driver=none']
    names=[]
    def run(role, code, data, network):
        name='scoped-canary-'+role+'-'+uuid.uuid4().hex[:12];names.append(name)
        return subprocess.run(docker+['run','--name',name,'-i',*common,'--network='+network,
                                     IMAGE,'/usr/bin/env','-i','PATH=/usr/local/bin:/usr/bin:/bin',
                                     'HOME=/tmp','python','-c',code],input=data,env=env,
                              capture_output=True,timeout=20,check=True).stdout
    try:
        # Preflight the cached image before any model call. Pulling is an explicit
        # setup step in the proposed workflow, not an implicit runtime fallback.
        subprocess.run(docker+['image','inspect',IMAGE],env=env,capture_output=True,check=True,timeout=10)
        broker='PROJECT='+repr(PROJECT)+'\nPAYLOAD_BYTES='+repr(json.dumps(PAYLOAD,separators=(',',':')).encode())+'\n'+BROKER
        require_fresh_admission()
        record.update(status='request_uncertain',provider_calls=1)
        save_evidence(record)
        raw=run('broker',broker,(secret+'\n').encode(),'bridge')
        record.update(response_sha256=hashlib.sha256(raw).hexdigest(),usage=safe_usage(raw))
        save_evidence(record)
        text,usage=validate(raw)
        result=json.loads(run('worker',WORKER,json.dumps({'text':text}).encode(),'none'))
        record.update(status='awaiting_review',usage=safe_usage(raw),checks=result,source=text)
        save_evidence(record)
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            f.write('Synthetic canary completed; two assertions passed; no publication. Reservation retained.\n')
    except BaseException:
        record['status']='uncertain' if record['provider_calls'] else 'not_dispatched'
        save_evidence(record)
        raise
    finally:
        for name in names:
            subprocess.run(docker+['rm','-f',name],env=env,capture_output=True,timeout=10,check=True)


if __name__=='__main__':
    try:
        if sys.argv[1:]==['--check-admission']: require_fresh_admission()
        elif sys.argv[1:]: raise ValueError('unsupported command')
        else: main()
    except BaseException:
        print('Scoped canary stopped; no retry; reservation retained',file=sys.stderr)
        sys.exit(2)
