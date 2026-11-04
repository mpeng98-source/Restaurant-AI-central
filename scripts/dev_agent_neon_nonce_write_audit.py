"""Protected Neon permit acceptance via audited function, never direct INSERT.

Requires a separately provisioned, isolated test reservation. Fails closed if
missing. Rollback-only; no Codex invocation.
"""
import os
import sys
import time
import json
import psycopg
from dev_agent_trusted_verifier import verify_and_consume


class RollbackTest(Exception):
    pass


def verify(url, key, envelope, *, run_id, issue, sha, project):
    if not url or not key or len(key) < 32:
        raise ValueError("missing protected verifier configuration")
    if not project.startswith("proj_acceptance_"):
        raise ValueError("only isolated acceptance projects permitted")
    with psycopg.connect(url, connect_timeout=8) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            if cur.fetchone() != ("dev_agent_control_db", "dev_agent_permit_verifier_safe"):
                raise ValueError("wrong verifier identity")
            cur.execute("SELECT has_table_privilege(current_user,'dev_agent_control.consumed_permit','INSERT')")
            if cur.fetchone()[0]:
                raise ValueError("verifier must not insert directly")
            cur.execute("SELECT has_function_privilege(current_user,'dev_agent_control.consume_verified_permit(text,bigint,bigint,text,text)','EXECUTE')")
            if not cur.fetchone()[0]:
                raise ValueError("missing narrowly scoped function permission")
        try:
            with conn.transaction():
                first = verify_and_consume(conn,envelope,key,now=int(time.time()),
                    run_id=run_id,issue_number=issue,head_sha=sha,project_id=project)
                second = verify_and_consume(conn,envelope,key,now=int(time.time()),
                    run_id=run_id,issue_number=issue,head_sha=sha,project_id=project)
                if first is not True or second is not False:
                    raise AssertionError("permit replay check failed")
                raise RollbackTest()
        except RollbackTest:
            pass
    return True


def main():
    try:
        envelope=json.loads(os.environ["DEV_AGENT_TEST_SIGNED_PERMIT"])
        verify(os.environ.get("DEV_AGENT_PERMIT_VERIFIER_DATABASE_URL"),
               os.environ.get("DEV_AGENT_PERMIT_HMAC_KEY","").encode(),
               envelope,run_id=int(os.environ["DEV_AGENT_TEST_RUN_ID"]),
               issue=int(os.environ["DEV_AGENT_TEST_ISSUE"]),
               sha=os.environ["DEV_AGENT_TEST_SHA"],
               project=os.environ["DEV_AGENT_TEST_PROJECT"])
    except Exception:
        print("Protected Neon permit audit denied; no Codex invocation",file=sys.stderr)
        return 2
    print("Protected Neon permit verification and rollback passed")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
