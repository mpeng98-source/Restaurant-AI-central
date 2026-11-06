"""Run candidate tests in the pinned, offline image; copy code via stdin, no mounts."""
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
IMAGE='python@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54'
paths=list((ROOT/'scripts').glob('*.py'))
for directory in ('canary_candidate','canary_transport','unattended_offline'):
    paths+=list((ROOT/'experiments'/directory).glob('*.py'))
bundle={str(p.relative_to(ROOT)):p.read_text() for p in paths}
code='''import json,pathlib,sys,unittest
root=pathlib.Path('/tmp/source')
for name,source in json.load(sys.stdin).items():
 p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(source)
start=root/'experiments/canary_candidate'
sys.path.insert(0,str(start))
suite=unittest.defaultTestLoader.discover(str(start),pattern='test_*.py')
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
'''
env=os.environ.copy()
for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):env.pop(key,None)
r=subprocess.run(['docker','--host=unix:///var/run/docker.sock','run','--rm','--pull=never',
                  '--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges',
                  '--user=65534:65534','--memory=256m','--cpus=1','--pids-limit=64',
                  '--tmpfs=/tmp:rw,nosuid,nodev,size=32m','-i',IMAGE,'/usr/bin/env','-i',
                  'PATH=/usr/local/bin:/usr/bin:/bin','PYTHONDONTWRITEBYTECODE=1','HOME=/tmp',
                  'python','-c',code],input=json.dumps(bundle),text=True,env=env,
                 capture_output=True,timeout=30)
print(r.stdout,end='');print(r.stderr,end='')
raise SystemExit(r.returncode)
