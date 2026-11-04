"""Read-only, fail-closed Neon verifier audit with sanitized stage diagnostics.

No credentials, SQL errors, row values or connection strings are logged.
"""
import os
import sys


class AuditDenied(Exception):
    def __init__(self, stage):
        self.stage = stage
        super().__init__("protected audit denied")


def audit(connect, url):
    if not url:
        raise AuditDenied("configuration")
    try:
        conn = connect(url, connect_timeout=8)
    except Exception:
        raise AuditDenied("connection") from None
    with conn:
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute("SELECT current_database(), current_user")
                    identity = cur.fetchone()
                except Exception:
                    raise AuditDenied("identity-query") from None
                if identity != ("dev_agent_control_db", "dev_agent_permit_verifier_safe"):
                    raise AuditDenied("identity-mismatch")
                try:
                    cur.execute("""
                        SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                               rolbypassrls, pg_has_role(oid, 'neon_superuser', 'MEMBER')
                        FROM pg_roles WHERE rolname = current_user
                    """)
                    attrs = cur.fetchone()
                except Exception:
                    raise AuditDenied("role-query") from None
                if attrs != (True, False, False, False, False, False):
                    raise AuditDenied("role-attributes")
                try:
                    cur.execute("""
                        SELECT has_database_privilege(current_user,current_database(),'CREATE'),
                               has_schema_privilege(current_user,'dev_agent_control','CREATE'),
                               has_table_privilege(current_user,'dev_agent_control.consumed_permit','INSERT, UPDATE, DELETE, TRUNCATE'),
                               has_any_column_privilege(current_user,'dev_agent_control.consumed_permit','INSERT'),
                               has_any_column_privilege(current_user,'dev_agent_control.consumed_permit','UPDATE'),
                               has_function_privilege(current_user,
                                 'dev_agent_control.consume_verified_permit(text,bigint,bigint,text,text)','EXECUTE')
                    """)
                    perms = cur.fetchone()
                except Exception:
                    raise AuditDenied("privilege-query") from None
                if perms != (False, False, False, False, False, False):
                    raise AuditDenied("privilege-policy")
        except AuditDenied:
            raise
        except Exception:
            raise AuditDenied("audit-runtime") from None
    return True


def main():
    try:
        import psycopg
        audit(psycopg.connect, os.environ.get("DEV_AGENT_PERMIT_VERIFIER_DATABASE_URL", ""))
    except AuditDenied as exc:
        print(f"Protected Neon verifier read-only audit denied: {exc.stage}", file=sys.stderr)
        return 2
    except Exception:
        print("Protected Neon verifier read-only audit denied: unexpected", file=sys.stderr)
        return 2
    print("Protected Neon verifier read-only audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
