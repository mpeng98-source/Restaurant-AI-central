#!/usr/bin/env python3
"""Fail-closed accounting and alert decisions. No network or writes.

OpenAI project costs are aggregated and delayed. A run-to-cost association
is a time-window estimate, NEVER an exact invoice for that Codex run.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re

RUN = re.compile(r"^[1-9][0-9]{0,19}$")
PROJECT = re.compile(r"^proj_[A-Za-z0-9_-]{1,128}$")


def money(value):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("invalid monetary value") from None
    if not d.is_finite() or d < 0:
        raise ValueError("invalid monetary value")
    return d


def reconcile(run: dict, cost_before: dict, cost_after: dict) -> dict:
    """Return a non-attributable project delta for an explicitly bounded run."""
    run_id = str(run.get("run_id", ""))
    project = run.get("project_id")
    if not RUN.fullmatch(run_id) or not isinstance(project, str) or not PROJECT.fullmatch(project):
        raise ValueError("invalid run or project")
    if run.get("status") != "completed" or run.get("codex_invoked") is not True:
        raise ValueError("run not completed with Codex invocation")
    start, end = run.get("started_at"), run.get("ended_at")
    if not isinstance(start, int) or not isinstance(end, int) or end <= start:
        raise ValueError("invalid run interval")
    if end - start > 4 * 3600:
        raise ValueError("run exceeds maximum correlation interval")
    for item in (cost_before, cost_after):
        if item.get("project_id") != project or item.get("source") != "openai_organization_costs":
            raise ValueError("untrusted cost source")
        if item.get("settlement_delay_possible") is not True:
            raise ValueError("cost settlement metadata required")
        if not isinstance(item.get("observed_at"), int):
            raise ValueError("missing observation time")
        if item.get("start_time") != cost_before.get("start_time") or item.get("end_time") != cost_before.get("end_time"):
            raise ValueError("cost windows differ")
        if item["start_time"] > start or item["end_time"] < end:
            raise ValueError("cost window does not cover run")
    if cost_after["observed_at"] <= cost_before["observed_at"]:
        raise ValueError("observations out of order")
    before, after = money(cost_before.get("reported_cost_usd")), money(cost_after.get("reported_cost_usd"))
    if after < before:
        raise ValueError("reported cost decreased; manual reconciliation needed")
    return {
        "run_id": run_id, "project_id": project, "project_reported_delta_usd": str(after-before),
        "attribution": "project_window_delta_not_run_cost",
        "exact_run_cost_known": False, "settlement_delay_possible": True,
    }


def quota_preflight(*, now: int, history: list[dict], max_daily_runs: int,
                    daily_budget_usd: str, estimated_max_run_usd: str,
                    reported_cost_usd: str, observed_at: int, max_staleness_seconds: int = 3600) -> dict:
    """Preflight only. Concurrent reservations MUST be atomic in a durable store."""
    if not isinstance(now, int) or not isinstance(observed_at, int) or observed_at > now or now-observed_at > max_staleness_seconds:
        return {"allowed": False, "reason": "missing or stale cost evidence"}
    if not isinstance(max_daily_runs, int) or isinstance(max_daily_runs, bool) or max_daily_runs < 1:
        return {"allowed": False, "reason": "invalid run cap"}
    if not isinstance(history, list):
        return {"allowed": False, "reason": "invalid history"}
    try:
        budget, estimate, spent = map(money, (daily_budget_usd, estimated_max_run_usd, reported_cost_usd))
    except ValueError:
        return {"allowed": False, "reason": "invalid cost evidence"}
    if estimate == 0:
        return {"allowed": False, "reason": "missing estimate"}
    day = datetime.fromtimestamp(now, timezone.utc).date()
    count = 0
    seen = set()
    for record in history:
        if not isinstance(record, dict) or not RUN.fullmatch(str(record.get("run_id", ""))):
            return {"allowed": False, "reason": "invalid history"}
        if record["run_id"] in seen:
            return {"allowed": False, "reason": "duplicate run record"}
        seen.add(record["run_id"])
        if record.get("state") not in ("reserved", "started", "completed", "failed"):
            return {"allowed": False, "reason": "invalid reservation state"}
        timestamp = record.get("reserved_at")
        if not isinstance(timestamp, int) or timestamp > now:
            return {"allowed": False, "reason": "invalid reservation time"}
        if datetime.fromtimestamp(timestamp, timezone.utc).date() == day:
            count += 1
    if count >= max_daily_runs:
        return {"allowed": False, "reason": "daily run quota reached"}
    if spent + estimate > budget:
        return {"allowed": False, "reason": "budget estimate exceeded"}
    return {"allowed": True, "reason": "preflight passed; atomic reservation still required",
            "runs_today": count, "remaining_estimated_usd": str(budget-spent-estimate)}


def alert_decision(*, ci_state: str, budget_allowed: bool, cost_data_stale: bool, run_failed: bool) -> dict:
    reasons = []
    if ci_state in ("failed", "unknown"):
        reasons.append("CI_REVIEW_REQUIRED")
    if not budget_allowed:
        reasons.append("BUDGET_OR_QUOTA_BLOCKED")
    if cost_data_stale:
        reasons.append("COST_DATA_STALE")
    if run_failed:
        reasons.append("CODEX_RUN_FAILED")
    return {"alert": bool(reasons), "codes": reasons, "notify": "owner_manual_review",
            "include_raw_logs": False}
