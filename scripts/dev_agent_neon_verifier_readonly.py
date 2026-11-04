"""Read-only Neon verifier identity and least-privilege audit.

No signing key, no reservation writes, no Codex invocation.
"""
import os
import sys


def audit(connect, url):
    if not url:
        raise ValueError("missing protected database URL")
    with connect(url, connect_timeout=8) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            if cur.fetchone() != ("dev_agent_control_db", "dev_agent_permit_verifier_safe"):
                raise ValueError("unexpected database identity")
            cur.execute("""
                SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                       rolbypassrls, pg_has_role(oid, 'neon_superuser', 'MEMBER')
                FROM pg_roles WHERE rolname = current_user
            """)
            row=cur.fetchone()
            if row is None or row != (True,False,False,False,False,False):
                raise ValueError("excessive role attributes")
            cur.execute("""
                SELECT has_database_privilege(current_user,current_database(),'CREATE'),
                       has_schema_privilege(current_user,'dev_agent_control','CREATE'),
                       has_table_privilege(current_user,'dev_agent_control.consumed_permit','INSERT, UPDATE, DELETE, TRUNCATE'),
                       has_any_column_privilege(current_user,'dev_agent_control.consumed_permit','INSERT'),
                       has_any_column_privilege(current_user,'dev_agent_control.consumed_permit','UPDATE'),
                       has_function_privilege(current_user,
                         'dev_agent_control.consume_verified_permit(text,bigint,bigint,text,text)','EXECUTE')
            """)
            perms=cur.fetchone()
            if perms != (False,False,False,False,False,False):
                raise ValueError("unexpected write or execution privileges")
    return True


def main():
    try:
        import psycopg
        audit(psycopg.connect,os.environ.get("DEV_AGENT_PERMIT_VERIFIER_DATABASE_URL",""))
    except Exception:
        print("Protected Neon verifier read-only audit denied",file=sys.stderr)
        return 2
    print("Protected Neon verifier read-only audit passed")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
