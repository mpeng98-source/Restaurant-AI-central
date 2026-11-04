#!/usr/bin/env python3
"""Control-plane preflight entrypoint. Fails closed without isolated credentials.

This entrypoint is intended for a separate, human-approved workflow job,
never for execution inside the Codex model's workspace.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    db_url = os.environ.get("DEV_AGENT_CONTROL_DATABASE_URL")
    if not db_url:
        print("Preflight denied: control-plane credential unavailable", file=sys.stderr)
        return 2
    if args.run_id <= 0 or args.issue <= 0:
        print("Preflight denied: invalid run or issue", file=sys.stderr)
        return 2
    try:
        import psycopg
        from dev_agent_durable_controls import reserve
        with psycopg.connect(db_url, connect_timeout=5) as conn:
            result = reserve(conn, run_id=args.run_id, issue_number=args.issue,
                             project_id=args.project_id, now=datetime.now(timezone.utc))
        if not result["allowed"]:
            print("Preflight denied: " + result["reason"], file=sys.stderr)
            return 2
        with open(args.output, "w") as f:
            json.dump({"approved": True, "run_id": args.run_id,
                       "issue_number": args.issue}, f)
        return 0
    except Exception:
        print("Preflight denied: control-plane verification failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
