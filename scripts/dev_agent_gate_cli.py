"""Protected workflow adapter. Inputs come from trusted needs/job context only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from dev_agent_execution_gate import Context, REPOSITORY, WORKFLOW, select, recheck, reserve, authorize, admit, service_identity
from dev_agent_accounting_cli import read_envelope
from dev_agent_cost_evidence import Producer, ingest_cost
from dev_agent_signed_evidence import canonical
from dev_agent_snapshot import snapshot


def context():
    if os.environ.get("GITHUB_EVENT_NAME")!="workflow_dispatch": raise ValueError("manual only")
    if os.environ.get("GITHUB_WORKFLOW_REF")!=REPOSITORY+"/"+WORKFLOW+"@refs/heads/main":
        raise ValueError("untrusted workflow source")
    return Context(os.environ["GITHUB_REPOSITORY"],WORKFLOW,os.environ["GITHUB_REF"],
                   os.environ["GITHUB_SHA"],int(os.environ["GITHUB_RUN_ID"]),
                   int(os.environ["GITHUB_RUN_ATTEMPT"]),int(os.environ["REQUESTED_ISSUE"]),
                   os.environ["PROJECT_ID"]).validate()


def output(name,value):
    encoded=canonical(value).decode()
    if len(encoded.encode())>49152: raise ValueError("oversized workflow output")
    with open(os.environ["GITHUB_OUTPUT"],"a") as file:file.write(name+"="+encoded+"\n")


def main(argv=None):
    try:
        command=(argv or sys.argv[1:])[0]
        ctx=context();now=int(time.time())
        if command=="select":
            plan=select(snapshot(ctx.repository),ctx)
            output("plan",plan)
        elif command=="admit":
            plan=json.loads(os.environ["PLAN_JSON"])
            recheck(snapshot(ctx.repository),plan,ctx)
            admit(json.loads(os.environ["AUTHORIZATION_JSON"]),plan,ctx=ctx,now=int(time.time()))
            # The model receives task data, never the permit or protected keys.
            Path("agent-task.md").write_text("UNTRUSTED APPROVED TASK DATA\n"+canonical(plan["task"]).decode()+"\n")
        elif command=="ingest":
            import psycopg
            with psycopg.connect(os.environ["DEV_AGENT_COST_WRITER_DATABASE_URL"],autocommit=True,connect_timeout=8) as db:
                service_identity(db,"dev_agent_cost_writer_v27")
                producer=Producer(ctx.repository,ctx.workflow,ctx.head_sha,ctx.run_id,ctx.attempt)
                digest=ingest_cost(db,read_envelope('protected-input/cost-envelope.json'),
                                   os.environ['DEV_AGENT_COST_SIGNING_KEY'].encode(),
                                   producer=producer,project_id=ctx.project_id,now=now)
                output('receipt',{'cost_digest':digest})
        elif command in {"reserve","authorize"}:
            import psycopg
            plan=json.loads(os.environ["PLAN_JSON"])
            # Approval labels/body and duplicate PR state are checked again
            # after environment approval, before either protected mutation.
            recheck(snapshot(ctx.repository),plan,ctx)
            current=subprocess.check_output(["gh","api",f"repos/{ctx.repository}/git/ref/heads/main","--jq",".object.sha"],text=True,timeout=30).strip()
            if current!=ctx.head_sha: raise ValueError("main advanced")
            key=os.environ["DEV_AGENT_PERMIT_HMAC_KEY"].encode()
            url=os.environ["DEV_AGENT_RESERVER_DATABASE_URL" if command=="reserve" else "DEV_AGENT_VERIFIER_DATABASE_URL"]
            with psycopg.connect(url,autocommit=True,connect_timeout=8) as db:
                service_identity(db,"dev_agent_reserver_v27" if command=="reserve" else "dev_agent_verifier_v27")
                if command=="reserve":
                    result=reserve(db,plan,key,ctx=ctx,cost_digest=os.environ["COST_DIGEST"],now=now)
                    output("permit",result)
                else:
                    result=authorize(db,plan,json.loads(os.environ["PERMIT_JSON"]),key,ctx=ctx,now=now)
                    output("authorization",result)
        elif command=="failure":
            import psycopg
            with psycopg.connect(os.environ["DEV_AGENT_FAILURE_DATABASE_URL"],autocommit=True,connect_timeout=8) as db:
                service_identity(db,"dev_agent_failure_v27")
                db.execute("SELECT dev_agent_accounting.mark_failed(%s,%s)",(ctx.run_id,ctx.project_id))
            # A failure/cancel never releases money automatically. Even lost
            # outputs stay reserved for an independently reviewed decision.
        else:raise ValueError("unknown protected command")
    except Exception:
        print("Protected execution gate denied",file=sys.stderr)
        return 2
    print("Protected execution gate passed")
    return 0


if __name__=="__main__":raise SystemExit(main())
