"""Conservative accounting policy; pure functions, not an active spend gate.

Treat already-settled reservations as included in reported project costs.
Only *outstanding* reservations add to the reported amount. Never infer
settlement from elapsed time or from a failed GitHub job alone.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

CAP = Decimal("10")
RESERVE = Decimal("5")
MAX_RUNS = 6
ACTIVE = {"reserved", "started", "failed_unreconciled"}
FINAL = {"settled", "cancelled_verified"}


def amount(x):
    try:
        d = Decimal(str(x))
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError("invalid amount") from None
    if not d.is_finite() or d < 0:
        raise ValueError("invalid amount")
    return d


def assess(*, now: datetime, observed_at: datetime, reported_usd,
           reservations: list[dict], max_age_seconds: int = 3600) -> dict:
    if now.tzinfo is None or observed_at.tzinfo is None:
        return {"allowed": False, "reason": "missing timezone"}
    now = now.astimezone(timezone.utc)
    observed_at = observed_at.astimezone(timezone.utc)
    if observed_at > now or (now-observed_at).total_seconds() > max_age_seconds:
        return {"allowed": False, "reason": "stale cost evidence"}
    try:
        reported = amount(reported_usd)
    except ValueError:
        return {"allowed": False, "reason": "invalid reported cost"}
    if not isinstance(reservations, list):
        return {"allowed": False, "reason": "invalid reservations"}
    seen = set()
    pending = Decimal(0)
    attempts = 0
    day = now.date().isoformat()
    for item in reservations:
        if not isinstance(item, dict) or item.get("utc_day") != day:
            return {"allowed": False, "reason": "missing or cross-day reservation context"}
        rid, state = item.get("run_id"), item.get("state")
        if not isinstance(rid, int) or isinstance(rid, bool) or rid <= 0 or rid in seen:
            return {"allowed": False, "reason": "invalid or duplicate run"}
        seen.add(rid)
        if state not in ACTIVE | FINAL:
            return {"allowed": False, "reason": "unknown settlement state"}
        attempts += 1
        if state in ACTIVE:
            pending += RESERVE
    if attempts >= MAX_RUNS:
        return {"allowed": False, "reason": "daily run limit"}
    # Pending reservations are conservatively additional to reported costs.
    # This is a safety estimate, not an API billing hard cap.
    if reported + pending + RESERVE > CAP:
        return {"allowed": False, "reason": "budget estimate exceeded",
                "estimated_exposure_usd": str(reported+pending)}
    return {"allowed": True, "reason": "accounting preflight only",
            "estimated_exposure_usd": str(reported+pending+RESERVE),
            "remaining_attempts": MAX_RUNS-attempts}


def settlement_transition(old: str, new: str, *, verified: bool) -> bool:
    if old in FINAL:
        return False
    if old not in ACTIVE or new not in FINAL:
        return False
    return verified is True
