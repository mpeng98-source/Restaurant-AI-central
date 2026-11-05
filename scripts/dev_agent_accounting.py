"""Protected transactional accounting and one-use authorization, inactive.

No model invocation. Use separate roles/keys for cost ingestion, reservation,
settlement and permit verification. A returned True authorizes no other job:
workflow enforcement must be separately reviewed before any activation.
"""
from __future__ import annotations
import hashlib
import re
import secrets

from dev_agent_cost_evidence import authenticate, integer, project, timestamp, require_idle
from dev_agent_signed_evidence import canonical, sign, verify


def binding(run_id, issue_number, head_sha, project_id):
    integer(run_id)
    integer(issue_number)
    if not isinstance(head_sha, str) or not re.fullmatch(r"[a-f0-9]{40}", head_sha):
        raise ValueError("invalid SHA")
    project(project_id)


def reserve_and_sign(conn, key, *, run_id, issue_number, head_sha, project_id,
                     cost_digest, now):
    binding(run_id,issue_number,head_sha,project_id)
    integer(now)
    if not isinstance(cost_digest,str) or not re.fullmatch(r"[a-f0-9]{64}",cost_digest):
        raise ValueError("invalid cost binding")
    # Prepare signature before mutation: missing/weak key cannot leave a reserve.
    envelope = sign({"kind":"codex_permit", "run_id":run_id,"issue_number":issue_number,
                     "head_sha":head_sha,"project_id":project_id,"issued_at":now,
                     "expires_at":now+120,"nonce":secrets.token_hex(24)},key)
    require_idle(conn)
    with conn.transaction():
        row = conn.execute("SELECT dev_agent_accounting.reserve_run(%s,%s,%s,%s,%s)",
                           (run_id,issue_number,head_sha,project_id,cost_digest)).fetchone()
        if row is None or row[0] is not True:
            raise ValueError("reservation denied")
    return envelope


def consume(conn, envelope, key, *, run_id, issue_number, head_sha, project_id, now):
    binding(run_id,issue_number,head_sha,project_id)
    body = verify(envelope,key,kind="codex_permit",now=now,run_id=run_id,
                  issue_number=issue_number,head_sha=head_sha,project_id=project_id)
    require_idle(conn)
    with conn.transaction():
        row = conn.execute("SELECT dev_agent_accounting.consume_permit(%s,%s,%s,%s,%s,%s,%s)",
                           (body["nonce"],run_id,issue_number,head_sha,project_id,
                            timestamp(body["issued_at"]),timestamp(body["expires_at"]))).fetchone()
        return row is not None and row[0] is True


def finalize(conn, envelope, key, *, producer, run_id, issue_number, head_sha, project_id, now):
    binding(run_id,issue_number,head_sha,project_id)
    body = authenticate(envelope,key,kind="settlement_review_v1",now=now,producer=producer)
    expected = {"run_id":run_id,"issue_number":issue_number,"head_sha":head_sha,"project_id":project_id}
    if body.get("binding") != expected:
        raise ValueError("settlement binding mismatch")
    integer(body["binding"].get("run_id"))
    integer(body["binding"].get("issue_number"))
    decision = body.get("decision")
    if decision not in {"settled","cancelled_verified"}:
        raise ValueError("invalid settlement")
    # A human-controlled reviewer attests these facts after checking evidence.
    # Costs API totals, job failure, and elapsed time cannot assert them.
    required = "billing_finality_reviewed" if decision=="settled" else "never_started_reviewed"
    if body.get(required) is not True:
        raise ValueError("missing independent review")
    reference, digest = body.get("review_reference"), body.get("cost_digest")
    if (not isinstance(reference,str) or not re.fullmatch(r"[A-Za-z0-9_./:#-]{1,200}",reference)
            or not isinstance(digest,str) or not re.fullmatch(r"[a-f0-9]{64}",digest)):
        raise ValueError("invalid review proof")
    finished = timestamp(body.get("finished_at"))
    if body["finished_at"]>now:
        raise ValueError("future finish")
    proof = hashlib.sha256(canonical(body)).hexdigest()
    require_idle(conn)
    with conn.transaction():
        row = conn.execute("SELECT dev_agent_accounting.finalize_run(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                           (proof,run_id,issue_number,head_sha,project_id,decision,digest,
                            finished,reference)).fetchone()
        return row is not None and row[0] is True
