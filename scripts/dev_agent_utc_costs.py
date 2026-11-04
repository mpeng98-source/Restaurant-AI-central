#!/usr/bin/env python3
"""UTC-day OpenAI Costs API collector, fail-closed and read-only.

No database credential is used here. The result must be independently
authenticated before a protected DB writer imports it.
"""
from datetime import datetime, timezone
from dev_agent_openai_costs import sum_project_costs


def collect_utc_day(fetch, *, project_id: str, now: datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError("timezone-aware observation required")
    now = now.astimezone(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start, end = int(midnight.timestamp()), int(now.timestamp())
    if end <= start:
        raise ValueError("empty UTC-day window")
    result = sum_project_costs(fetch, start, end, project_id)
    if result.get("project_id") != project_id or result.get("source") != "openai_organization_costs":
        raise ValueError("untrusted cost response")
    return {**result, "observed_at": end, "utc_day": midnight.date().isoformat(),
            "window_start": start, "window_end": end,
            "attribution": "project_reported_cost_not_per_run",
            "settlement_delay_possible": True}
