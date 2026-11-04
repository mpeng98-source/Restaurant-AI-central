"""Read-only check of a separately provisioned Neon permit ledger.

This does not consume a real permit, change database state, or call Codex.
"""
import os
import sys

def verify(connect, url):
    if not url:
        raise ValueError("missing connection")
    with connect(url, connect_timeout=8) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            if cur.fetchone() != ("dev_agent_control_db", "dev_agent_runner"):
                raise ValueError("unexpected database identity")
            cur.execute("SELECT to_regclass('dev_agent_control.consumed_permit')")
            if cur.fetchone()[0] is None:
                raise ValueError("permit ledger not provisioned")
            cur.execute("""
                SELECT has_table_privilege(current_user,
                       'dev_agent_control.consumed_permit','SELECT')
            """)
            if cur.fetchone()[0] is not True:
                raise ValueError("missing read access")
    return True

def main():
    try:
        import psycopg
        verify(psycopg.connect, os.environ.get("DEV_AGENT_CONTROL_DATABASE_URL"))
    except Exception:
        print("Protected Neon permit-ledger audit denied", file=sys.stderr)
        return 2
    print("Protected Neon permit-ledger read-only audit passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
