#!/usr/bin/env python3
"""Neon live write-path acceptance, fully rolled back. No Codex or real budget."""
import os
import secrets
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal

def run(connect, reserve, url):
    if not url:
        raise ValueError("missing control database URL")
    now = datetime.now(timezone.utc)
    run_id = secrets.randbelow(10**12) + 10**12
    issue = secrets.randbelow(10**10) + 10**10
    project = "proj_acceptance_" + secrets.token_hex(10)
    with connect(url, connect_timeout=8) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), current_user")
                if cur.fetchone() != ("dev_agent_control_db", "dev_agent_runner"):
                    raise ValueError("unexpected database or role")
                # Synthetic evidence, scoped to this transaction only.
                cur.execute("""
                    INSERT INTO dev_agent_control.daily_budget
                    (project_id, utc_day, max_runs, daily_budget_usd, reported_usd, cost_observed_at)
                    VALUES (%s, %s, 6, 10, 0, %s)
                """, (project, now.date(), now))
            first = reserve(conn, run_id=run_id, issue_number=issue, project_id=project, now=now)
            if first.get("allowed") is not True:
                raise AssertionError("fresh synthetic evidence did not allow reservation")
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT reserved_usd FROM dev_agent_control.daily_budget
                    WHERE project_id=%s AND utc_day=%s
                """, (project, now.date()))
                if Decimal(str(cur.fetchone()[0])) != Decimal("5"):
                    raise AssertionError("reserved balance not 5")
            duplicate = reserve(conn, run_id=run_id, issue_number=issue, project_id=project, now=now)
            if duplicate.get("allowed") is not False or duplicate.get("reason") != "run already reserved":
                raise AssertionError("duplicate run not rejected")
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE dev_agent_control.daily_budget SET cost_observed_at=%s
                    WHERE project_id=%s AND utc_day=%s
                """, (now - timedelta(hours=2), project, now.date()))
            stale = reserve(conn, run_id=run_id+1, issue_number=issue+1, project_id=project, now=now)
            if stale.get("allowed") is not False or stale.get("reason") != "missing or stale cost evidence":
                raise AssertionError("stale cost not rejected")
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM dev_agent_control.run_reservation WHERE project_id=%s", (project,))
                if cur.fetchone()[0] != 1:
                    raise AssertionError("unexpected reservation count")
        finally:
            # Even on success, discard all synthetic records.
            conn.rollback()
    # Independent connection confirms rollback persisted nothing.
    with connect(url, connect_timeout=8) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM dev_agent_control.daily_budget WHERE project_id=%s", (project,))
            if cur.fetchone()[0] != 0:
                raise AssertionError("synthetic budget unexpectedly persisted")
            cur.execute("SELECT count(*) FROM dev_agent_control.run_reservation WHERE project_id=%s", (project,))
            if cur.fetchone()[0] != 0:
                raise AssertionError("synthetic reservation unexpectedly persisted")
    return True

def main():
    try:
        import psycopg
        from dev_agent_durable_controls import reserve
        run(psycopg.connect, reserve, os.environ.get("DEV_AGENT_CONTROL_DATABASE_URL", ""))
    except Exception:
        print("Neon rollback acceptance FAILED (details withheld)", file=sys.stderr)
        return 2
    print("Neon rollback acceptance PASSED: write, duplicate, stale, zero persistent test records")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
