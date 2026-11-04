"""Trusted manual execution admission. No model, GitHub writes or credentials.

The authorization receipt is transported ONLY through trusted GitHub job outputs,
not user/artifact inputs. Re-running a job changes attempt and invalidates it.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import re
import secrets

from dev_agent_cost_evidence import integer, project, require_idle, timestamp
from dev_agent_prepare_task import prepare
from dev_agent_signed_evidence import canonical, sign, verify

REPOSITORY="mpeng98-source/Restaurant-AI-central"
WORKFLOW=".github/workflows/chubby-dev-agent-gated.yml"


@dataclass(frozen=True)
class Context:
    repository: str
    workflow: str
    ref: str
    head_sha: str
    run_id: int
    attempt: int
    issue_number: int
    project_id: str

    def validate(self):
        if self.repository!=REPOSITORY or self.workflow!=WORKFLOW or self.ref!="refs/heads/main":
            raise ValueError("untrusted workflow context")
        integer(self.run_id);integer(self.attempt);integer(self.issue_number)
        if not isinstance(self.head_sha,str) or not re.fullmatch(r"[a-f0-9]{40}",self.head_sha):
            raise ValueError("invalid source SHA")
        project(self.project_id)
        return self

    def binding(self):
        return dict(run_id=self.run_id,issue_number=self.issue_number,
                    head_sha=self.head_sha,project_id=self.project_id)


def digest_task(task):
    return hashlib.sha256(canonical(task)).hexdigest()


def select(snapshot,ctx):
    ctx.validate()
    task=prepare(snapshot,ctx.issue_number)
    if task.get("selected") is not True: raise ValueError("no approved safe task")
    task={k:task[k] for k in ("number","title","body")}
    return {"context":asdict(ctx),"task":task,"task_digest":digest_task(task)}


def check_plan(plan,ctx):
    ctx.validate()
    if not isinstance(plan,dict) or plan.get("context")!=asdict(ctx):
        raise ValueError("plan context mismatch")
    if type(plan["context"].get("run_id")) is not int or type(plan["context"].get("attempt")) is not int:
        raise ValueError("invalid integer context")
    task=plan.get("task")
    if (not isinstance(task,dict) or set(task)!={"number","title","body"}
            or type(task.get("number")) is not int or task["number"]!=ctx.issue_number
            or digest_task(task)!=plan.get("task_digest")):
        raise ValueError("task digest mismatch")
    return plan


def recheck(snapshot,plan,ctx):
    check_plan(plan,ctx)
    if select(snapshot,ctx)!=plan:
        raise ValueError("task changed or approval revoked")


def reserve(conn,plan,key,*,ctx,cost_digest,now):
    check_plan(plan,ctx);integer(now)
    if not isinstance(cost_digest,str) or not re.fullmatch(r"[a-f0-9]{64}",cost_digest):
        raise ValueError("invalid cost digest")
    envelope=sign({"kind":"codex_permit",**ctx.binding(),"issued_at":now,"expires_at":now+120,
                   "nonce":secrets.token_hex(24),"attempt":ctx.attempt,"task_digest":plan["task_digest"]},key)
    require_idle(conn)
    with conn.transaction():
        row=conn.execute("SELECT dev_agent_accounting.reserve_task(%s,%s,%s,%s,%s,%s,%s)",
                         (ctx.run_id,ctx.attempt,ctx.issue_number,ctx.head_sha,ctx.project_id,
                          cost_digest,plan["task_digest"])).fetchone()
        if row is None or row[0] is not True: raise ValueError("reservation denied")
    return envelope


def authorize(conn,plan,envelope,key,*,ctx,now):
    check_plan(plan,ctx)
    body=verify(envelope,key,kind="codex_permit",now=now,**ctx.binding())
    if type(body.get("attempt")) is not int or body["attempt"]!=ctx.attempt or body.get("task_digest")!=plan["task_digest"]:
        raise ValueError("permit task or attempt mismatch")
    require_idle(conn)
    with conn.transaction():
        row=conn.execute("SELECT dev_agent_accounting.authorize_task(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                         (body["nonce"],ctx.run_id,ctx.attempt,ctx.issue_number,ctx.head_sha,
                          ctx.project_id,plan["task_digest"],timestamp(body["issued_at"]),timestamp(body["expires_at"]))).fetchone()
        if row is None or row[0] is not True: raise ValueError("permit consumption denied")
    return {"allowed":True,"context":asdict(ctx),"task_digest":plan["task_digest"],
            "authorized_at":now,"admit_before":now+300}


def admit(receipt,plan,*,ctx,now):
    check_plan(plan,ctx);integer(now)
    if not isinstance(receipt,dict) or set(receipt)!={"allowed","context","task_digest","authorized_at","admit_before"}:
        raise ValueError("missing authorization")
    if receipt["allowed"] is not True or receipt["context"]!=asdict(ctx) or receipt["task_digest"]!=plan["task_digest"]:
        raise ValueError("authorization binding mismatch")
    Context(**receipt["context"]).validate()
    issued,expires=integer(receipt["authorized_at"]),integer(receipt["admit_before"])
    if not issued<=now<expires or expires-issued!=300: raise ValueError("admission expired")
    return True


def execute_simulated(receipt,plan,callback,*,ctx,now):
    """Test harness only. Production model invocation is a gated workflow step."""
    admit(receipt,plan,ctx=ctx,now=now)
    return callback(plan["task"])
