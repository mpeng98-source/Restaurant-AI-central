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
                # Inspect privileges through catalog object OIDs. PostgreSQL
                # resolves text relation/function names under schema USAGE,
                # which this read-only verifier intentionally does NOT have.
                # Catalog lookups do not grant data access; missing objects
                # return no row and fail closed in the loop below.
                table_oid = """(
                    SELECT c.oid FROM pg_catalog.pg_class AS c
                    JOIN pg_catalog.pg_namespace AS n ON n.oid=c.relnamespace
                    WHERE n.nspname='dev_agent_control'
                      AND c.relname='consumed_permit'
                      AND c.relkind IN ('r','p')
                )"""
                function_oid = """(
                    SELECT p.oid FROM pg_catalog.pg_proc AS p
                    JOIN pg_catalog.pg_namespace AS n ON n.oid=p.pronamespace
                    WHERE n.nspname='dev_agent_control'
                      AND p.proname='consume_verified_permit'
                      AND p.proargtypes='25 20 20 25 25'::pg_catalog.oidvector
                )"""
                checks = (
                    ("database-create", "SELECT has_database_privilege(current_user,current_database(),'CREATE')"),
                    ("schema-create", "SELECT has_schema_privilege(current_user,'dev_agent_control','CREATE')"),
                    ("table-insert", "SELECT has_table_privilege(current_user," + table_oid + ",'INSERT')"),
                    ("table-update", "SELECT has_table_privilege(current_user," + table_oid + ",'UPDATE')"),
                    ("table-delete", "SELECT has_table_privilege(current_user," + table_oid + ",'DELETE')"),
                    ("table-truncate", "SELECT has_table_privilege(current_user," + table_oid + ",'TRUNCATE')"),
                    ("column-insert", "SELECT has_any_column_privilege(current_user," + table_oid + ",'INSERT')"),
                    ("column-update", "SELECT has_any_column_privilege(current_user," + table_oid + ",'UPDATE')"),
                    ("function-execute", "SELECT has_function_privilege(current_user," + function_oid + ",'EXECUTE')"),
                )
                for stage, sql in checks:
                    try:
                        cur.execute(sql)
                        value = cur.fetchone()
                    except Exception:
                        raise AuditDenied("privilege-query-" + stage) from None
                    if value is None or len(value) != 1 or value[0] is not False:
                        raise AuditDenied("privilege-policy-" + stage)
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
