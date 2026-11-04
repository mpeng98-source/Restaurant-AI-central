"""Transparent one-statement transport for tools that split SQL on semicolons.

Decoded source is exactly the three reviewed files, minus their outer transaction
markers. DO executes the entire bundle atomically. No credentials or activation.
"""
import base64
import hashlib
from pathlib import Path

FILES=('ops/migrations/0001_dev_agent_accounting.sql',
       'ops/migrations/0002_dev_agent_execution_gate.sql','ops/dev-agent-v27-provision-review.sql')


def bundle(root):
    source='\n'.join((Path(root)/p).read_text() for p in FILES)
    source='\n'.join(line for line in source.splitlines() if line.strip() not in {'BEGIN;','COMMIT;'})
    payload=base64.b64encode(source.encode()).decode()
    body="BEGIN EXECUTE convert_from(decode('"+payload+"','base64'),'UTF8'); END"
    # E-string octal escapes keep raw semicolons out of naive tool splitters.
    escaped=body.replace('\\','\\\\').replace("'","''").replace(';','\\073')
    statement="DO E'"+escaped+"'"
    return source,statement,hashlib.sha256(source.encode()).hexdigest()


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    print(bundle(root)[1])
