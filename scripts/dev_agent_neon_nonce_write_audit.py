"""Protected Neon permit consumption acceptance. All writes rolled back.

Requires a separately provisioned verifier role with audited permissions.
Never run with the restaurant role or database owner.
"""
import os
import secrets
import sys
from concurrent.futures import ThreadPoolExecutor
import psycopg
from dev_agent_permit_ledger import consume_nonce


def verify(url):
    if not url:
        raise ValueError("missing protected verifier connection")
    nonce = secrets.token_hex(24)
    run_id = secrets.randbelow(10**11) + 10**11
    # All acceptance writes remain inside ONE uncommitted transaction.
    # This validates a duplicate attempt within the transaction, not
    # concurrent transactions across connections (covered by ephemeral CI).
    with psycopg.connect(url, connect_timeout=8) as db:
        try:
            with db.cursor() as cur:
                cur.execute("SELECT current_database(), current_user")
                name, role = cur.fetchone()
                if name != "dev_agent_control_db" or role != "dev_agent_permit_verifier_login":
                    raise ValueError("unexpected database or verifier identity")
                cur.execute("SELECT to_regclass('dev_agent_control.consumed_permit')")
                if cur.fetchone()[0] is None:
                    raise ValueError("permit ledger missing")
            first = consume_nonce(db, nonce=nonce, run_id=run_id, issue_number=39,
                                  head_sha="a"*40, project_id="proj_acceptance")
            second = consume_nonce(db, nonce=nonce, run_id=run_id, issue_number=39,
                                   head_sha="a"*40, project_id="proj_acceptance")
            if first is not True or second is not False:
                raise AssertionError("nonce replay rejection failed")
        finally:
            db.rollback()
    with psycopg.connect(url, connect_timeout=8) as db:
        row = db.execute("SELECT count(*) FROM dev_agent_control.consumed_permit WHERE nonce=%s", (nonce,)).fetchone()
        if row[0] != 0:
            raise AssertionError("test nonce persisted")
    return True


def main():
    try:
        verify(os.environ.get("DEV_AGENT_PERMIT_VERIFIER_DATABASE_URL", ""))
    except Exception:
        print("Protected Neon nonce rollback audit denied", file=sys.stderr)
        return 2
    print("Protected Neon nonce rollback audit passed; no test records persisted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
