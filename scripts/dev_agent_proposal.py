"""Validate a model proposal on a fresh trusted checkout, then publish Draft only.

Never execute model-supplied tests/code/commands. The publisher alone holds its
scoped GitHub token; no model job shares its runner or filesystem state.
"""
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.request import Request, build_opener

from dev_agent_accounting_cli import NoRedirect
from dev_agent_execution_gate import check_plan
from dev_agent_gate_cli import context


def validate(proposal,root):
    root=root.resolve()
    if not isinstance(proposal,dict) or set(proposal)!={"files"}:
        raise ValueError("invalid proposal")
    files=proposal["files"]
    if not isinstance(files,list) or not 1<=len(files)<=3:raise ValueError("invalid file count")
    if len(json.dumps(proposal).encode())>49152:raise ValueError("oversized proposal")
    seen=set()
    for item in files:
        if not isinstance(item,dict) or set(item)!={"path","content"}:raise ValueError("invalid file")
        path,content=item["path"],item["content"]
        if not isinstance(path,str) or not isinstance(content,str) or not content.strip():raise ValueError("invalid content")
        parts=PurePosixPath(path).parts
        if (PurePosixPath(path).is_absolute() or ".." in parts or "\\" in path
                or not re.fullmatch(r"[A-Za-z0-9_./-]+",path) or path in seen
                or any(p.startswith(".") for p in parts)):
            raise ValueError("unsafe path")
        if not (path.startswith("backend/tests/") and path.endswith(".py")
                or path.startswith("frontend/tests/") and path.endswith((".ts",".tsx",".mjs"))
                or path.startswith("docs/sprint-2") and path.endswith(".md")):
            raise ValueError("outside pilot scope")
        local=root/path
        if any(p.is_symlink() for p in [local,*local.parents]) or not local.is_file():
            raise ValueError("only existing regular files permitted")
        if "\x00" in content or len(content.encode())>32768:raise ValueError("invalid content")
        if local.read_text()==content:raise ValueError("no change")
        seen.add(path)
    return files


def publish(api,files,*,ctx,base_tree):
    branch=f"agent/issue-{ctx.issue_number}-run-{ctx.run_id}-attempt-{ctx.attempt}"
    tree=api("POST","git/trees",{"base_tree":base_tree,"tree":[
        {"path":f["path"],"mode":"100644","type":"blob","content":f["content"]} for f in files]})
    commit=api("POST","git/commits",{"message":f"agent: bounded proposal for issue #{ctx.issue_number}",
                                       "tree":tree["sha"],"parents":[ctx.head_sha]})
    # No update/force endpoint: an existing branch is an error, not overwritten.
    api("POST","git/refs",{"ref":"refs/heads/"+branch,"sha":commit["sha"]})
    return api("POST","pulls",{"title":f"Agent proposal: issue #{ctx.issue_number}","head":branch,"base":"main","draft":True,
                                 "body":f"Bounded model proposal for #{ctx.issue_number}. Unreviewed; CI and human approval required. The publisher did not execute model-supplied code or tests. No merge or deployment. Gate run {ctx.run_id}, attempt {ctx.attempt}, source {ctx.head_sha}."})


def main():
    try:
        ctx=context()
        plan=json.loads(os.environ["PLAN_JSON"]);check_plan(plan,ctx)
        # This job is reachable only through generate's successful job result.
        root=Path.cwd()
        actual=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
        if actual!=ctx.head_sha:raise ValueError("checkout mismatch")
        files=validate(json.loads(os.environ["PROPOSAL_JSON"]),root)
        base_tree=subprocess.check_output(["git","rev-parse","HEAD^{tree}"],text=True).strip()
        token=os.environ["CHUBBY_DEV_AGENT_PR_TOKEN"]
        if not token:raise ValueError("missing publication credential")
        transport=build_opener(NoRedirect)
        def api(method,path,body):
            data=json.dumps(body).encode()
            url="https://api.github.com/repos/"+ctx.repository+"/"+path
            with transport.open(Request(url,data=data,method=method,headers={"Authorization":"Bearer "+token,
                    "Accept":"application/vnd.github+json","Content-Type":"application/json"}),timeout=30) as response:
                return json.load(response)
        pr=publish(api,files,ctx=ctx,base_tree=base_tree)
        if pr.get("draft") is not True:raise ValueError("draft publication not confirmed")
        print("Draft proposal published: #"+str(int(pr["number"])))
    except Exception:
        print("Draft proposal publication denied",file=sys.stderr)
        return 2
    return 0


if __name__=="__main__":raise SystemExit(main())
