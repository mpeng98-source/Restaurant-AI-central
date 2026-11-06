"""Persist only validated trusted exception metadata; never raw env or outputs."""
import json
import os
from pathlib import Path
import re

FIELDS={'mode','prior_cost_state','request_ceiling_usd','claim_consumed','run_id',
        'head_sha','task_digest','request_digest','settled'}


def persist(raw, directory, *, run_id, head):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError('duplicate metadata')
            out[k]=v
        return out
    if not isinstance(raw,str) or len(raw.encode())>2048:raise ValueError('oversized metadata')
    record=json.loads(raw,object_pairs_hook=pairs)
    if not isinstance(record,dict) or set(record)!=FIELDS:raise ValueError('metadata fields')
    if (record['mode']!='issue-58-unknown-cost-once-v1' or record['prior_cost_state']!='unknown'
            or record['request_ceiling_usd']!='5.000000' or record['claim_consumed'] is not True
            or record['settled'] is not False or type(record['run_id']) is not int
            or record['run_id']!=run_id or record['head_sha']!=head):
        raise ValueError('metadata context')
    for key,size in [('head_sha',40),('task_digest',64),('request_digest',64)]:
        if not isinstance(record[key],str) or not re.fullmatch('[a-f0-9]{'+str(size)+'}',record[key]):
            raise ValueError('metadata digest')
    target=Path(directory)/'scoped-canary-exception.json'
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(record,f,sort_keys=True)
        f.flush();os.fsync(f.fileno())
    return target


if __name__=='__main__':
    persist(os.environ['EXCEPTION_JSON'],os.environ['RUNNER_TEMP'],
            run_id=int(os.environ['GITHUB_RUN_ID']),head=os.environ['GITHUB_SHA'])
