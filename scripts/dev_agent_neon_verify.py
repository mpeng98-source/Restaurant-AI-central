#!/usr/bin/env python3
"""Read-only verification of an isolated Neon Dev Agent control database.

Never print connection details, credentials, or row values.
"""
import os
import sys

TABLES = {"daily_budget", "run_reservation", "cost_observation", "run_usage", "alert_outbox"}


def verify(connect, url: str) -> None:
    if not url or not url.startswith(("postgresql://", "postgres://")):
        raise ValueError("invalid connection configuration")
    with connect(url, connect_timeout=8) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            database, role = cur.fetchone()
            if database != "dev_agent_control_db" or role != "dev_agent_runner":
                raise ValueError("unexpected database identity")
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='dev_agent_control'
            """)
            found = {row[0] for row in cur.fetchall()}
            if not TABLES.issubset(found):
                raise ValueError("missing control tables")
            cur.execute("""
                SELECT has_schema_privilege(current_user, 'dev_agent_control', 'USAGE'),
                       has_schema_privilege(current_user, 'dev_agent_control', 'CREATE')
            """)
            usage, create = cur.fetchone()
            if usage is not True or create is not False:
                raise ValueError("unsafe schema permissions")
            for table in TABLES:
                cur.execute("SELECT has_table_privilege(current_user, %s, 'SELECT')",
                            (f"dev_agent_control.{table}",))
                if cur.fetchone()[0] is not True:
                    raise ValueError("missing read permission")


def main() -> int:
    url = os.environ.get("DEV_AGENT_CONTROL_DATABASE_URL", "")
    try:
        import psycopg
        verify(psycopg.connect, url)
    except Exception:
        print("Neon control-plane verification denied (configuration or permission failure)", file=sys.stderr)
        return 2
    print("Neon control-plane read-only verification passed; five tables and restricted role verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
