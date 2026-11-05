"""Authenticated cost transport between isolated collector and database writer.

Only the protected collector may sign API results. HMAC authenticates that
collector, not OpenAI itself. Never sign an uploaded user-supplied report.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import re
from urllib.parse import urlencode

from dev_agent_openai_costs import ENDPOINT
from dev_agent_signed_evidence import canonical, sign


class MissingProjectCosts(ValueError):
    """The API returned no project rows; that cannot establish zero spend."""


def integer(value, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError("invalid integer")
    return value


def money(value):
    # Transport decimals as strings; never round a cost down into a budget.
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,12}(\.\d{1,6})?", value):
        raise ValueError("invalid money")
    result = Decimal(value)
    if not result.is_finite() or result < 0:
        raise ValueError("invalid money")
    return result


def project(value):
    if not isinstance(value, str) or not re.fullmatch(r"proj_[A-Za-z0-9_-]{1,128}", value):
        raise ValueError("invalid project")
    return value


def timestamp(value):
    return datetime.fromtimestamp(integer(value), timezone.utc)


def require_idle(conn):
    # An outer transaction could roll back after a permit is returned. Every
    # service operation must commit durably before publishing its result.
    if conn.info.transaction_status != 0:
        raise ValueError("dedicated idle connection required")


@dataclass(frozen=True)
class Producer:
    repository: str
    workflow: str
    sha: str
    run_id: int
    attempt: int

    def validate(self):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            raise ValueError("invalid repository")
        if not re.fullmatch(r"\.github/workflows/[A-Za-z0-9_.-]+\.yml", self.workflow):
            raise ValueError("invalid workflow")
        if not re.fullmatch(r"[a-f0-9]{40}", self.sha):
            raise ValueError("invalid source SHA")
        integer(self.run_id)
        integer(self.attempt)
        return self


def authenticate(envelope, key, *, kind, now, producer):
    producer.validate()
    integer(now)
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError("missing protected signing key")
    if not isinstance(envelope, dict) or set(envelope) != {"payload", "signature"}:
        raise ValueError("invalid envelope")
    body, signature = envelope["payload"], envelope["signature"]
    if not isinstance(body, dict) or not isinstance(signature, str):
        raise ValueError("invalid signature")
    expected = hmac.new(key, canonical(body), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("signature mismatch")
    issued, expires = integer(body.get("issued_at")), integer(body.get("expires_at"))
    if issued > now or now >= expires or not 0 < expires-issued <= 300:
        raise ValueError("expired evidence")
    if body.get("kind") != kind or body.get("producer") != asdict(producer):
        raise ValueError("untrusted producer")
    # No Python bool/integer equivalence in authenticated context.
    actual = body.get("producer", {})
    integer(actual.get("run_id"))
    integer(actual.get("attempt"))
    return body


def collect_cost(fetch, *, project_id, utc_day, now):
    """Strict project/day collector. Empty rows remain unknown, never zero proof.

    fetch must be the fixed HTTPS transport defined by the protected CLI.
    Pages and bucket ranges are validated before a report can be signed.
    """
    project(project_id)
    integer(now)
    day = datetime.strptime(utc_day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start = int(day.timestamp())
    end = min(now, start+86400)
    if start >= end or now-start > 7*86400:
        raise ValueError("invalid collection day")
    cursor, seen, total, rows, buckets = None, set(), Decimal(0), 0, set()
    for _ in range(30):
        params = {"start_time": start, "end_time": end, "bucket_width": "1d",
                  "project_ids": project_id, "group_by": "project_id", "limit": 1}
        if cursor:
            params["page"] = cursor
        response = fetch(ENDPOINT + "?" + urlencode(params))
        if not isinstance(response, dict) or not isinstance(response.get("data"), list):
            raise ValueError("invalid page")
        if type(response.get("has_more")) is not bool:
            raise ValueError("ambiguous pagination")
        for bucket in response["data"]:
            if not isinstance(bucket, dict) or not isinstance(bucket.get("results"), list):
                raise ValueError("invalid bucket")
            bounds = (bucket.get("start_time"), bucket.get("end_time"))
            # A daily Costs bucket can end at midnight after the requested end.
            if (type(bounds[0]) is not int or type(bounds[1]) is not int
                    or bounds[0] != start or not end <= bounds[1] <= start+86400
                    or bounds in buckets):
                raise ValueError("overlapping or out-of-window bucket")
            buckets.add(bounds)
            for row in bucket["results"]:
                if not isinstance(row, dict) or row.get("project_id") != project_id:
                    raise ValueError("wrong project")
                amount = row.get("amount")
                if not isinstance(amount, dict) or amount.get("currency", "").lower() != "usd":
                    raise ValueError("invalid currency")
                try:
                    value = Decimal(str(amount.get("value")))
                except InvalidOperation:
                    raise ValueError("invalid amount") from None
                if not value.is_finite() or value < 0:
                    raise ValueError("invalid amount")
                total += value
                rows += 1
        next_page = response.get("next_page")
        if not response["has_more"]:
            if next_page:
                raise ValueError("ambiguous final page")
            break
        if not isinstance(next_page, str) or not next_page or next_page in seen:
            raise ValueError("missing or repeated page")
        seen.add(next_page)
        cursor = next_page
    else:
        raise ValueError("incomplete pagination")
    if rows == 0:
        raise MissingProjectCosts("missing project costs are unknown")
    # Round UP if API precision exceeds the database's six decimal places.
    from decimal import ROUND_CEILING
    reported = format(total.quantize(Decimal("0.000001"), rounding=ROUND_CEILING), "f")
    money(reported)
    return {"project_id": project_id, "utc_day": utc_day, "window_start": start,
            "window_end": end, "observed_at": now, "reported_usd": reported,
            "source": "openai_organization_costs", "project_rows": rows}


def sign_cost(report, key, *, producer, now):
    producer.validate()
    return sign({"kind": "cost_observation_v1", "producer": asdict(producer),
                 "issued_at": now, "expires_at": now+300, "report": report}, key)


def ingest_cost(conn, envelope, key, *, producer, project_id, now):
    body = authenticate(envelope, key, kind="cost_observation_v1", now=now, producer=producer)
    report = body.get("report")
    project(project_id)
    if not isinstance(report, dict) or report.get("project_id") != project_id:
        raise ValueError("project mismatch")
    if report.get("source") != "openai_organization_costs":
        raise ValueError("invalid source")
    integer(report.get("project_rows"))
    start, end, observed = (integer(report.get(k)) for k in ("window_start","window_end","observed_at"))
    day = timestamp(start)
    if (day.hour or day.minute or day.second or day.date().isoformat() != report.get("utc_day")
            or not start < end <= start+86400 or not end <= observed <= now
            or now-observed > 300 or body["issued_at"] != observed):
        raise ValueError("invalid observation window")
    value = money(report.get("reported_usd"))
    digest = hashlib.sha256(canonical(body)).hexdigest()
    require_idle(conn)
    with conn.transaction():
        conn.execute("SELECT dev_agent_accounting.ingest_cost(%s,%s,%s,%s,%s,%s,%s,%s)",
                     (digest,project_id,day.date(),timestamp(end),timestamp(observed),
                      value,producer.run_id,producer.attempt))
    return digest
