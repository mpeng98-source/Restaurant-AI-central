"""Unwired production-integration candidate; imports do not perform IO.

Must run only in the existing protected verifier job, using the existing
restricted verifier connection. A separately reviewed exact-run DB policy is
required. This is an exception to cost evidence, NOT evidence of zero cost.
"""
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from dev_agent_execution_gate import check_plan, recheck, service_identity


def consume(conn, plan, *, ctx, request_digest):
    check_plan(plan, ctx)
    if (ctx.issue_number != 58 or ctx.project_id != 'proj_Nkd1G85QX72VHwdQ8mEg8CRa'
            or ctx.attempt != 1):
        raise ValueError('exception scope denied')
    service_identity(conn, 'dev_agent_verifier_v27')
    # Existing helper verifies no enclosing transaction. Commit before returning.
    with conn.transaction():
        row = conn.execute('SELECT dev_agent_canary_exception.consume(%s,%s,%s,%s,%s,%s,%s)',
            (ctx.project_id, ctx.issue_number, ctx.run_id, ctx.attempt, ctx.head_sha,
             plan['task_digest'], request_digest)).fetchone()
        if row != (True,):
            raise ValueError('exception absent, expired, mismatched or already consumed')


def execute(conn, plan, *, ctx, request_digest, callback, clock=time.time):
    consume(conn, plan, ctx=ctx, request_digest=request_digest)
    # No refund, retry or rollback after this point, including callback failure.
    now = int(clock())
    receipt = {'allowed':True, 'context':asdict(ctx), 'task_digest':plan['task_digest'],
               'authorized_at':now, 'admit_before':now+300}
    return callback(receipt)


def main():
    from dev_agent_gate_cli import context
    from dev_agent_snapshot import snapshot
    import psycopg
    if os.environ.get('CANARY_EXCEPTION_MODE') != 'issue-58-unknown-cost-once-v1':
        raise ValueError('exception mode not explicitly selected')
    ctx = context()
    plan = json.loads(os.environ['PLAN_JSON'])
    recheck(snapshot(ctx.repository), plan, ctx)
    # Existing snapshot does not prove main's current SHA; check immediately.
    import subprocess
    current = subprocess.check_output(['gh','api',f'repos/{ctx.repository}/git/ref/heads/main',
                                      '--jq','.object.sha'],text=True,timeout=30).strip()
    if current != ctx.head_sha:
        raise ValueError('main advanced')
    spec = importlib.util.spec_from_file_location('reviewed_canary', ROOT/'experiments/canary_candidate/run.py')
    canary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(canary)
    digest = hashlib.sha256(json.dumps(canary.PAYLOAD,separators=(',',':')).encode()).hexdigest()
    def publish_receipt(receipt):
        # Trusted job output, not a user artifact. The separate generate job keeps
        # its existing API key; this verifier job never receives that key.
        from dev_agent_gate_cli import output
        output('authorization', receipt)
        output('exception', {'mode':'issue-58-unknown-cost-once-v1','prior_cost_state':'unknown',
                'request_ceiling_usd':'5.000000','claim_consumed':True,'run_id':ctx.run_id,
                'head_sha':ctx.head_sha,'task_digest':plan['task_digest'],
                'request_digest':digest,'settled':False})
    with psycopg.connect(os.environ['DEV_AGENT_VERIFIER_DATABASE_URL'],
                         autocommit=True,connect_timeout=8) as conn:
        execute(conn,plan,ctx=ctx,request_digest=digest,callback=publish_receipt)


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        print('One-shot exception stopped; claim may be consumed; never retry',file=sys.stderr)
        sys.exit(2)
