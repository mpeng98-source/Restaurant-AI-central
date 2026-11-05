#!/usr/bin/env python3
"""Read-only OpenAI organization Costs API collector (project scoped).

Requires an organization admin key. Never emits the key or raw API response.
Reports settled costs, not a real-time spend ceiling or per-agent attribution.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import json
import os
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://api.openai.com/v1/organization/costs"
MAX_PAGES = 30


def sum_project_costs(fetch, start: int, end: int, project_id: str) -> dict:
    if not project_id.startswith("proj_") or len(project_id) > 128:
        raise ValueError("invalid project")
    if end <= start or end - start > 86400 * 7:
        raise ValueError("invalid interval")
    total = Decimal("0")
    page = None
    seen = set()
    for _ in range(MAX_PAGES):
        params = {"start_time": start, "end_time": end, "bucket_width": "1d",
                  "group_by": "project_id", "limit": 31}
        if page:
            params["page"] = page
        response = fetch(ENDPOINT + "?" + urlencode(params))
        if not isinstance(response, dict) or not isinstance(response.get("data"), list):
            raise ValueError("invalid Costs API response")
        for bucket in response["data"]:
            if not isinstance(bucket, dict) or not isinstance(bucket.get("results"), list):
                raise ValueError("invalid cost bucket")
            for result in bucket["results"]:
                if result.get("project_id") != project_id:
                    continue
                amount = result.get("amount")
                if not isinstance(amount, dict) or str(amount.get("currency", "")).lower() != "usd":
                    raise ValueError("invalid currency")
                try:
                    value = Decimal(str(amount["value"]))
                except (InvalidOperation, KeyError, TypeError):
                    raise ValueError("invalid amount") from None
                if not value.is_finite() or value < 0:
                    raise ValueError("invalid amount")
                total += value
        page = response.get("next_page")
        if not page:
            return {"project_id": project_id, "start_time": start, "end_time": end,
                    "reported_cost_usd": str(total), "source": "openai_organization_costs",
                    "settlement_delay_possible": True}
        if not isinstance(page, str) or page in seen:
            raise ValueError("invalid pagination cursor")
        seen.add(page)
    raise ValueError("too many cost pages")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--start-time", type=int)
    parser.add_argument("--end-time", type=int)
    args = parser.parse_args()
    key = os.environ.get("OPENAI_ADMIN_KEY", "")
    if not key:
        print("OPENAI_ADMIN_KEY missing", file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc)
    end = args.end_time or int(now.timestamp())
    start = args.start_time or end - 86400

    def fetch(url):
        req = Request(url, headers={"Authorization": f"Bearer {key}",
                                    "Accept": "application/json"})
        with urlopen(req, timeout=30) as response:
            return json.load(response)

    try:
        result = sum_project_costs(fetch, start, end, args.project_id)
        with open(args.output, "w") as file:
            json.dump(result, file)
    except Exception:
        # Never print response bodies or credentials.
        try:
            os.unlink(args.output)
        except FileNotFoundError:
            pass
        print("Costs API collection failed closed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
