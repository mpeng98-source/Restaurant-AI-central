"""Trusted permit verification boundary. No Codex invocation or network listener.

The protected verifier job owns the HMAC key and separate verifier DB connection.
The Codex job must never receive either. This function is not a production gate
until the workflow, dedicated DB role and live acceptance are reviewed.
"""
from __future__ import annotations
import re
from dev_agent_signed_evidence import verify


def verify_and_consume(conn, envelope: dict, signing_key: bytes, *,
                       now: int, run_id: int, issue_number: int,
                       head_sha: str, project_id: str) -> bool:
    # Cryptographic checks MUST precede all database writes.
    payload = verify(envelope, signing_key, kind="codex_permit", now=now,
                     run_id=run_id, issue_number=issue_number,
                     head_sha=head_sha, project_id=project_id)
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
        raise ValueError("invalid run")
    if not isinstance(issue_number, int) or isinstance(issue_number, bool) or issue_number <= 0:
        raise ValueError("invalid issue")
    if not re.fullmatch(r"[a-f0-9]{40}", head_sha):
        raise ValueError("invalid SHA")
    # No SQL string interpolation. The SECURITY DEFINER function checks the
    # approved reservation and uses unique nonce + run constraints.
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                "SELECT dev_agent_control.consume_verified_permit(%s,%s,%s,%s,%s)",
                (payload["nonce"], run_id, issue_number, head_sha, project_id))
            row = cur.fetchone()
            return row is not None and row[0] is True
