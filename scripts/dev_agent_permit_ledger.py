"""Transactionally consume a verified permit nonce exactly once.

Must be called from a protected control-plane job with a separate DB role.
Never place signing or database credentials in the Codex execution job.
"""
import re


def consume_nonce(conn, *, nonce: str, run_id: int, issue_number: int,
                  head_sha: str, project_id: str) -> bool:
    if not re.fullmatch(r"[a-f0-9]{32,64}", nonce):
        raise ValueError("invalid nonce")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO dev_agent_control.consumed_permit
                (nonce, run_id, issue_number, head_sha, project_id)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (nonce) DO NOTHING RETURNING nonce
            """, (nonce, run_id, issue_number, head_sha, project_id))
            return cur.fetchone() is not None
