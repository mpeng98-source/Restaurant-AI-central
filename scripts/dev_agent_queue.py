#!/usr/bin/env python3
"""Pure, fail-closed issue queue selector for Chubby Dev Agent v2.1.

Input is a JSON object with issues and open PRs, supplied by a trusted
post-fetch workflow step. This program has no network access or GitHub writes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

APPROVED = "agent-approved"
SAFE = "agent-safe"
BLOCKED = {"agent-blocked", "agent-needs-human"}
HIGH_RISK = re.compile(
    r"\b(migrat(?:ion|e)|alembic|row.level.security|rls|authentication|"
    r"authorization|production|deploy(?:ment)?|secret|credential|"
    r"payment|payroll|schema|permissions?)\b", re.I
)
PR_PATTERN = re.compile(r"^Agent proposal: issue #(\d+)$")


def labels(issue: dict) -> set[str]:
    return {item["name"] if isinstance(item, dict) else item
            for item in issue.get("labels", [])}


def eligible(issue: dict, open_pr_numbers: set[int]) -> tuple[bool, str]:
    number = issue.get("number")
    if not isinstance(number, int) or number < 1:
        return False, "invalid issue number"
    if issue.get("state", "").upper() != "OPEN":
        return False, "not open"
    tags = labels(issue)
    if APPROVED not in tags or SAFE not in tags:
        return False, "missing explicit approval and safe classification"
    if tags & BLOCKED:
        return False, "blocked or human-only"
    if number in open_pr_numbers:
        return False, "draft proposal already open"
    title = issue.get("title", "")
    body = issue.get("body", "") or ""
    if not isinstance(title, str) or not isinstance(body, str):
        return False, "invalid issue content"
    if len(body) > 12000 or len(title) > 250:
        return False, "issue exceeds size limit"
    if HIGH_RISK.search(title + "\n" + body):
        return False, "potential high-risk work requires human triage"
    return True, "approved safe task"


def select_task(payload: dict, requested: int = 0) -> dict:
    issues = payload.get("issues", [])
    prs = payload.get("pull_requests", [])
    if not isinstance(issues, list) or not isinstance(prs, list):
        raise ValueError("Invalid GitHub data shape")
    open_pr_numbers = set()
    for pr in prs:
        if pr.get("state", "").upper() != "OPEN":
            continue
        match = PR_PATTERN.fullmatch(pr.get("title", ""))
        if match:
            open_pr_numbers.add(int(match.group(1)))
    candidates = sorted(issues, key=lambda item: item.get("number", 0))
    if requested:
        candidates = [item for item in candidates if item.get("number") == requested]
        if not candidates:
            return {"selected": False, "reason": "requested issue not found"}
    for issue in candidates:
        ok, reason = eligible(issue, open_pr_numbers)
        if ok:
            return {"selected": True, "number": issue["number"],
                    "title": issue["title"], "reason": reason}
        if requested:
            return {"selected": False, "reason": reason}
    return {"selected": False, "reason": "no eligible safe issue"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--issue", type=int, default=0)
    args = parser.parse_args()
    if args.issue < 0:
        parser.error("--issue must be nonnegative")
    try:
        payload = json.loads(args.input.read_text())
        result = select_task(payload, args.issue)
    except (ValueError, KeyError, TypeError) as exc:
        print(f"Queue validation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
