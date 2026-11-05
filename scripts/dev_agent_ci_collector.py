#!/usr/bin/env python3
"""Read-only GitHub Actions job metadata collector. No raw logs or model input."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_PAGES = 20


def collect(repo: str, run_id: int) -> dict:
    if not REPO.fullmatch(repo) or any(s in (".", "..") or s.startswith("-") for s in repo.split("/")):
        raise ValueError("invalid repository")
    if run_id <= 0:
        raise ValueError("invalid run ID")
    raw = subprocess.run(
        ["gh", "api", "--paginate", "--slurp",
         f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"],
        capture_output=True, text=True, check=True, timeout=90
    ).stdout
    pages = json.loads(raw)
    if not isinstance(pages, list) or not pages or len(pages) > MAX_PAGES:
        raise ValueError("invalid or excessive pagination")
    jobs = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("jobs"), list):
            raise ValueError("malformed GitHub jobs response")
        for job in page["jobs"]:
            if not isinstance(job, dict) or not isinstance(job.get("name"), str):
                raise ValueError("malformed job")
            jobs.append({
                "name": job["name"][:100],
                "status": job.get("status"),
                "conclusion": job.get("conclusion"),
            })
            if len(jobs) > 2000:
                raise ValueError("too many jobs")
    if not jobs:
        raise ValueError("no jobs returned")
    return {"run_id": run_id, "jobs": jobs}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        args.output.write_text(json.dumps(collect(args.repo, args.run_id)))
    except (ValueError, TypeError, KeyError, subprocess.SubprocessError, json.JSONDecodeError):
        args.output.unlink(missing_ok=True)
        print("GitHub job collection failed closed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
