#!/usr/bin/env python3
"""Offline, read-only reliability preflight for Chubby Dev Agent.

Consumes sanitized GitHub job metadata, not logs or secrets. Estimates a
conservative spend ceiling; actual API charges must be checked separately.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

FAILURES = {"failure", "timed_out", "cancelled", "action_required"}
PASS = {"success"}
PENDING = {"queued", "in_progress", "waiting", "pending", "requested"}


def triage(jobs: list[dict]) -> dict:
    if not isinstance(jobs, list) or not jobs:
        return {"state": "unknown", "reason": "no jobs"}
    failed, pending, unknown = [], [], []
    for job in jobs:
        if not isinstance(job, dict):
            return {"state": "unknown", "reason": "invalid job metadata"}
        name = job.get("name")
        status = job.get("status")
        conclusion = job.get("conclusion")
        if not isinstance(name, str) or not name or not isinstance(status, str):
            return {"state": "unknown", "reason": "invalid job metadata"}
        # Do not pass arbitrary names or log contents to a model.
        if conclusion in FAILURES:
            failed.append(name[:100])
        elif status in PENDING or (status != "completed" and conclusion is None):
            pending.append(name[:100])
        elif status == "completed" and conclusion in PASS:
            continue
        else:
            unknown.append(name[:100])
    if failed:
        return {"state": "failed", "failed_jobs": len(failed), "retry": False,
                "reason": "manual review required"}
    if pending:
        return {"state": "pending", "pending_jobs": len(pending), "retry": False}
    if unknown:
        return {"state": "unknown", "unknown_jobs": len(unknown), "retry": False}
    return {"state": "passed", "retry": False}


def budget_preflight(limit_usd: str, estimated_max_usd: str,
                     spent_usd: str, runs_today: int, max_runs: int) -> dict:
    try:
        values = [Decimal(x) for x in (limit_usd, estimated_max_usd, spent_usd)]
    except (InvalidOperation, ValueError, TypeError):
        return {"allowed": False, "reason": "invalid budget"}
    if not all(x.is_finite() and x >= 0 for x in values):
        return {"allowed": False, "reason": "invalid budget"}
    if any(isinstance(x, bool) or not isinstance(x, int) for x in (runs_today, max_runs)):
        return {"allowed": False, "reason": "invalid run count"}
    if max_runs < 1 or runs_today < 0 or runs_today >= max_runs:
        return {"allowed": False, "reason": "run limit reached"}
    if values[1] == 0:
        return {"allowed": False, "reason": "missing nonzero cost estimate"}
    if values[2] + values[1] > values[0]:
        return {"allowed": False, "reason": "estimated budget exceeded"}
    return {"allowed": True, "reason": "within configured estimate"}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--jobs", type=Path, required=True)
    p.add_argument("--daily-limit-usd", required=True)
    p.add_argument("--estimated-run-max-usd", required=True)
    p.add_argument("--spent-today-usd", required=True)
    p.add_argument("--runs-today", required=True, type=int)
    p.add_argument("--max-runs", required=True, type=int)
    a = p.parse_args()
    data = json.loads(a.jobs.read_text())
    result = {
        "ci": triage(data["jobs"]),
        "budget": budget_preflight(a.daily_limit_usd, a.estimated_run_max_usd,
                                   a.spent_today_usd, a.runs_today, a.max_runs),
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
