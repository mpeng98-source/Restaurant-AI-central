#!/usr/bin/env python3
"""Atomic Postgres quota reservation and deduplicated alert outbox.

Requires an isolated control-plane DB credential. Never provide it to Codex.
Not wired to the production workflow until real Postgres acceptance passes.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
import subprocess
import re

RUN_LIMIT = 6
DAY_LIMIT = Decimal("10")
PER_RUN_RESERVE = Decimal("5")
MAX_COST_AGE_SECONDS = 3600
ALERT_CODES = frozenset({"CI_REVIEW_REQUIRED", "BUDGET_OR_QUOTA_BLOCKED",
                         "COST_DATA_STALE", "CODEX_RUN_FAILED"})


def reserve(conn, *, run_id: int, issue_number: int, project_id: str, now: datetime) -> dict:
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
        raise ValueError("invalid run id")
    if not isinstance(issue_number, int) or isinstance(issue_number, bool) or issue_number <= 0:
        raise ValueError("invalid issue number")
    if not isinstance(project_id, str) or not project_id.startswith("proj_"):
        raise ValueError("invalid project")
    if now.tzinfo is None:
        raise ValueError("timezone required")
    day = now.astimezone(timezone.utc).date()
    # Transaction serializes all reservations for one project and UTC day.
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO dev_agent_control.daily_budget
                  (project_id, utc_day, max_runs, daily_budget_usd)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (project_id, utc_day) DO NOTHING
            """, (project_id, day, RUN_LIMIT, DAY_LIMIT))
            cur.execute("""
                SELECT reserved_usd, reported_usd, cost_observed_at
                FROM dev_agent_control.daily_budget
                WHERE project_id=%s AND utc_day=%s FOR UPDATE
            """, (project_id, day))
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("budget row unavailable")
            reserved, reported, observed = row
            if observed is None or observed.tzinfo is None or observed > now or (now-observed).total_seconds() > MAX_COST_AGE_SECONDS:
                return {"allowed": False, "reason": "missing or stale cost evidence"}
            cur.execute("""
                SELECT issue_number FROM dev_agent_control.run_reservation WHERE run_id=%s
            """, (run_id,))
            prior = cur.fetchone()
            if prior:
                return {"allowed": False, "reason": "run already reserved"}
            cur.execute("""
                SELECT count(*) FROM dev_agent_control.run_reservation
                WHERE project_id=%s AND utc_day=%s
            """, (project_id, day))
            if cur.fetchone()[0] >= RUN_LIMIT:
                return {"allowed": False, "reason": "daily run quota reached"}
            # Reserve a conservative allowance against settled reported spend.
            # Never double-count already reserved amounts as exact settled costs.
            if Decimal(str(reported)) + Decimal(str(reserved)) + PER_RUN_RESERVE > DAY_LIMIT:
                return {"allowed": False, "reason": "budget reservation exceeded"}
            cur.execute("""
                INSERT INTO dev_agent_control.run_reservation
                (run_id, project_id, utc_day, issue_number, reserved_usd)
                VALUES (%s, %s, %s, %s, %s)
            """, (run_id, project_id, day, issue_number, PER_RUN_RESERVE))
            cur.execute("""
                UPDATE dev_agent_control.daily_budget
                SET reserved_usd=reserved_usd+%s
                WHERE project_id=%s AND utc_day=%s
            """, (PER_RUN_RESERVE, project_id, day))
            return {"allowed": True, "reason": "atomic reservation committed", "run_id": run_id}


def queue_alert(conn, *, alert_key: str, run_id: int, code: str) -> bool:
    if code not in ALERT_CODES or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", alert_key):
        raise ValueError("invalid alert")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO dev_agent_control.alert_outbox (alert_key, run_id, alert_code)
                VALUES (%s,%s,%s) ON CONFLICT (alert_key) DO NOTHING
                RETURNING alert_key
            """, (alert_key, run_id, code))
            return cur.fetchone() is not None


def deliver_one_alert(conn, *, repo: str) -> dict:
    """Claim a pending alert; use gh issue create as an owner-visible notification.

    Failures leave a 'sending' record for manual reconciliation, avoiding
    blind retries that could duplicate GitHub issues.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or ".." in repo:
        raise ValueError("invalid repository")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""
                SELECT alert_key, run_id, alert_code FROM dev_agent_control.alert_outbox
                WHERE state='pending' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
            """)
            row = cur.fetchone()
            if row is None:
                return {"status": "empty"}
            key, run_id, code = row
            cur.execute("UPDATE dev_agent_control.alert_outbox SET state='sending' WHERE alert_key=%s", (key,))
    # No raw logs, costs, secrets or user-controlled issue text in notification.
    title = f"Chubby Dev Agent alert: {code}"
    body = f"Automated control-plane alert. Run ID: {run_id}. Alert key: {key}. Human review required."
    result = subprocess.run(["gh", "issue", "create", "--repo", repo,
                             "--title", title, "--body", body],
                            check=True, capture_output=True, text=True, timeout=30)
    url = result.stdout.strip()
    import re
    match = re.search(r"/issues/(\d+)$", url)
    if not match:
        raise RuntimeError("GitHub issue created but ID could not be verified; manual reconciliation required")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE dev_agent_control.alert_outbox
                SET state='sent', delivered_at=now(), github_issue_number=%s
                WHERE alert_key=%s AND state='sending'
            """, (int(match.group(1)), key))
    return {"status": "sent", "issue_number": int(match.group(1))}


def record_cost_observation(conn, *, project_id: str, observed_at: datetime,
                            window_start: datetime, window_end: datetime,
                            reported_usd: str) -> None:
    """Persist trusted collector output and refresh the UTC-day budget row.

    Call only from a trusted post-collector process with verified project ID.
    """
    from dev_agent_cost_controls import money
    if not isinstance(project_id, str) or not project_id.startswith("proj_"):
        raise ValueError("invalid project")
    if any(t.tzinfo is None for t in (observed_at, window_start, window_end)):
        raise ValueError("timezone required")
    if window_end <= window_start or observed_at < window_end:
        raise ValueError("invalid observation window")
    value = money(reported_usd)
    day = observed_at.astimezone(timezone.utc).date()
    utc_start = window_start.astimezone(timezone.utc)
    utc_end = window_end.astimezone(timezone.utc)
    if utc_start.date() != day or utc_start.hour != 0 or utc_start.minute != 0 or utc_start.second != 0 or utc_start.microsecond != 0 or utc_end.date() != day:
        raise ValueError("budget evidence must cover the current UTC day from midnight")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO dev_agent_control.cost_observation
                (project_id, observed_at, window_start, window_end, reported_cost_usd, source)
                VALUES (%s,%s,%s,%s,%s,'openai_organization_costs')
                ON CONFLICT (project_id, observed_at) DO NOTHING
            """, (project_id, observed_at, window_start, window_end, value))
            cur.execute("""
                INSERT INTO dev_agent_control.daily_budget
                (project_id, utc_day, max_runs, daily_budget_usd)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (project_id, utc_day) DO NOTHING
            """, (project_id, day, RUN_LIMIT, DAY_LIMIT))
            cur.execute("""
                UPDATE dev_agent_control.daily_budget
                SET reported_usd=%s, cost_observed_at=%s
                WHERE project_id=%s AND utc_day=%s
                  AND (cost_observed_at IS NULL OR cost_observed_at < %s)
            """, (value, observed_at, project_id, day, observed_at))


def record_run_usage(conn, *, run_id: int, started_at: datetime,
                     ended_at: datetime, model: str,
                     input_tokens: int | None, output_tokens: int | None) -> None:
    """Store trusted runner telemetry, never model-supplied usage claims."""
    if run_id <= 0 or started_at.tzinfo is None or ended_at.tzinfo is None or ended_at <= started_at:
        raise ValueError("invalid run interval")
    if not isinstance(model, str) or not model or len(model) > 128:
        raise ValueError("invalid model")
    for n in (input_tokens, output_tokens):
        if n is not None and (not isinstance(n, int) or isinstance(n, bool) or n < 0):
            raise ValueError("invalid token count")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO dev_agent_control.run_usage
                (run_id, started_at, ended_at, model, input_tokens, output_tokens)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (run_id) DO NOTHING
            """, (run_id, started_at, ended_at, model, input_tokens, output_tokens))
