"""Manual protected service commands. Never invokes Codex or provisions roles.

No credentials on the command line or in output. No arbitrary API endpoints,
redirects, user reports to sign, or automatic settlement proof generation.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler

from dev_agent_accounting import reserve_and_sign, consume, finalize
from dev_agent_cost_evidence import Producer, collect_cost, sign_cost, ingest_cost
from dev_agent_openai_costs import ENDPOINT


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("redirect denied")


def read_envelope(path):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError("duplicate JSON key")
            result[key]=value
        return result
    with open(path,"rb") as file:
        raw=file.read(65537)
    if len(raw)>65536: raise ValueError("oversized evidence")
    return json.loads(raw,object_pairs_hook=unique)


def write_result(path,body):
    # Exclusive create prevents accidentally reusing/overwriting a permit.
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w") as file:
        json.dump(body,file,allow_nan=False)


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=("collect","ingest","reserve","consume","settle"))
    parser.add_argument("--project-id",required=True)
    parser.add_argument("--input")
    parser.add_argument("--output")
    parser.add_argument("--utc-day")
    parser.add_argument("--producer-run",type=int)
    parser.add_argument("--producer-attempt",type=int)
    parser.add_argument("--producer-sha")
    parser.add_argument("--producer-workflow",default=".github/workflows/chubby-dev-agent-authenticated-costs.yml")
    parser.add_argument("--run-id",type=int)
    parser.add_argument("--issue",type=int)
    parser.add_argument("--head-sha")
    parser.add_argument("--cost-digest")
    args=parser.parse_args(argv)
    try:
        if args.output and Path(args.output).exists(): raise ValueError("output already exists")
        now=int(time.time())
        if args.command=="collect":
            # Only protected main code may obtain Admin Key + collector key.
            if os.environ.get("GITHUB_REF")!="refs/heads/main": raise ValueError("main only")
            producer=Producer(os.environ["GITHUB_REPOSITORY"],args.producer_workflow,
                              os.environ["GITHUB_SHA"],int(os.environ["GITHUB_RUN_ID"]),
                              int(os.environ["GITHUB_RUN_ATTEMPT"]))
            expected_workflow=producer.repository+"/"+producer.workflow+"@refs/heads/main"
            if (producer.repository!="mpeng98-source/Restaurant-AI-central"
                    or os.environ.get("GITHUB_WORKFLOW_REF")!=expected_workflow):
                raise ValueError("untrusted workflow identity")
            key=os.environ["OPENAI_ADMIN_KEY"]
            if not key or not args.output: raise ValueError("missing collector configuration")
            transport=build_opener(NoRedirect)
            def fetch(url):
                if not url.startswith(ENDPOINT+"?"): raise ValueError("untrusted endpoint")
                with transport.open(Request(url,headers={"Authorization":"Bearer "+key,
                      "Accept":"application/json"}),timeout=30) as response:
                    raw=response.read(2*1024*1024+1)
                    if len(raw)>2*1024*1024: raise ValueError("oversized API response")
                    return json.loads(raw,parse_float=str)
            day=args.utc_day or datetime.now(timezone.utc).date().isoformat()
            report=collect_cost(fetch,project_id=args.project_id,utc_day=day,now=now)
            result=sign_cost(report,os.environ["DEV_AGENT_COST_SIGNING_KEY"].encode(),producer=producer,now=now)
        else:
            import psycopg
            role_key={"ingest":"DEV_AGENT_COST_WRITER_DATABASE_URL",
                      "reserve":"DEV_AGENT_RESERVER_DATABASE_URL",
                      "consume":"DEV_AGENT_VERIFIER_DATABASE_URL",
                      "settle":"DEV_AGENT_SETTLEMENT_DATABASE_URL"}[args.command]
            binding=dict(run_id=args.run_id,issue_number=args.issue,head_sha=args.head_sha,project_id=args.project_id)
            with psycopg.connect(os.environ[role_key],autocommit=True,connect_timeout=8) as db:
                if args.command in {"ingest","settle"}:
                    # Expected identity MUST come from the trusted caller's job
                    # context/configuration, never copied from the input file.
                    producer=Producer("mpeng98-source/Restaurant-AI-central",args.producer_workflow,
                                      args.producer_sha,args.producer_run,args.producer_attempt)
                if args.command=="ingest":
                    digest=ingest_cost(db,read_envelope(args.input),os.environ["DEV_AGENT_COST_SIGNING_KEY"].encode(),
                                       producer=producer,project_id=args.project_id,now=now)
                    result={"cost_digest":digest}
                elif args.command=="reserve":
                    if not args.output: raise ValueError("permit output required")
                    result=reserve_and_sign(db,os.environ["DEV_AGENT_PERMIT_HMAC_KEY"].encode(),
                                            cost_digest=args.cost_digest,now=now,**binding)
                elif args.command=="consume":
                    if not consume(db,read_envelope(args.input),os.environ["DEV_AGENT_PERMIT_HMAC_KEY"].encode(),now=now,**binding):
                        raise ValueError("permit denied")
                    result={"consumed":True}
                else:
                    if not finalize(db,read_envelope(args.input),os.environ["DEV_AGENT_SETTLEMENT_REVIEW_KEY"].encode(),
                                    producer=producer,now=now,**binding):
                        raise ValueError("settlement denied")
                    result={"finalized":True}
        if args.output: write_result(args.output,result)
    except Exception:
        # Do not print exception messages, raw evidence, connection strings,
        # API errors or credential values. Failure never authorizes execution.
        print("Protected accounting command denied",file=sys.stderr)
        return 2
    print("Protected accounting command passed; no Codex invocation")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
