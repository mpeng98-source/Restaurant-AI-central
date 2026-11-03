#!/usr/bin/env python3
"""Read-only, paginated GitHub snapshot for the Dev Agent issue selector."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_PAGES = 50
MAX_RECORDS = 5000


def fetch_pages(repo: str, resource: str) -> list[dict]:
    if not REPOSITORY.fullmatch(repo):
        raise ValueError("Invalid repository identifier")
    if resource not in {"issues", "pulls"}:
        raise ValueError("Invalid GitHub resource")
    result = subprocess.run(
        ["gh", "api", "--paginate", "--slurp",
         f"repos/{repo}/{resource}?state=open&per_page=100"],
        capture_output=True, text=True, check=True, timeout=90,
    )
    pages = json.loads(result.stdout)
    if not isinstance(pages, list) or len(pages) > MAX_PAGES:
        raise ValueError("Invalid or excessive GitHub pagination")
    records: list[dict] = []
    for page in pages:
        if not isinstance(page, list):
            raise ValueError("Invalid GitHub page")
        if len(page) > 100:
            raise ValueError("GitHub page exceeds limit")
        for record in page:
            if not isinstance(record, dict):
                raise ValueError("Invalid GitHub record")
            records.append(record)
            if len(records) > MAX_RECORDS:
                raise ValueError("Too many GitHub records")
    return records


def snapshot(repo: str) -> dict:
    issues_raw = fetch_pages(repo, "issues")
    prs_raw = fetch_pages(repo, "pulls")
    issues = [
        {"number": x["number"], "state": x["state"], "title": x["title"],
         "body": x.get("body") or "", "labels": x["labels"]}
        for x in issues_raw if "pull_request" not in x
    ]
    prs = [
        {"number": x["number"], "state": x["state"], "title": x["title"]}
        for x in prs_raw
    ]
    return {"issues": issues, "pull_requests": prs}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = snapshot(args.repo)
        # Do not write incomplete snapshots.
        data = json.dumps(result, ensure_ascii=False)
        args.output.write_text(data)
        print(f"Fetched {len(result['issues'])} open issues and {len(result['pull_requests'])} open PRs")
        return 0
    except (ValueError, KeyError, TypeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        args.output.unlink(missing_ok=True)
        print(f"Snapshot failed closed: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
