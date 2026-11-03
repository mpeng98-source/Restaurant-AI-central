#!/usr/bin/env python3
"""Fail-closed change gate for the Chubby Dev Agent v2."""
from __future__ import annotations

import pathlib
import subprocess
import sys

ALLOWED_PREFIXES = (
    "backend/tests/",
    "frontend/tests/",
    "frontend/app/inventory/",
    "frontend/app/inventory-approvals/",
    "docs/sprint-2",
)
ALLOWED_FILES = {"frontend/app/inventory/page.tsx"}
FORBIDDEN_COMPONENTS = {"..", ".git", ".github", ".env", "node_modules", ".next", "__pycache__"}
EXCLUDED = {"agent-task.md", "dev-agent-report.md", "dev-agent.patch"}


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def changed_files() -> list[str]:
    raw = subprocess.check_output(["git", "status", "--porcelain=v1", "-z"])
    parts = raw.decode("utf-8", "replace").split("\0")
    paths: list[str] = []
    i = 0
    while i < len(parts) and parts[i]:
        entry = parts[i]
        status = entry[:2]
        path = entry[3:]
        if status[0] in "RC" or status[1] in "RC":
            raise ValueError("Renames/copies require human review")
        paths.append(path)
        i += 1
    return paths


def safe_path(value: str) -> bool:
    p = pathlib.PurePosixPath(value)
    if p.is_absolute() or any(part in FORBIDDEN_COMPONENTS for part in p.parts):
        return False
    if value in EXCLUDED or value.endswith((".pem", ".key", ".env", ".lock")):
        return False
    return value in ALLOWED_FILES or any(value.startswith(prefix) for prefix in ALLOWED_PREFIXES)


def main() -> int:
    paths = changed_files()
    candidates = [p for p in paths if p not in EXCLUDED]
    if not candidates:
        print("No code changes produced; no PR will be created.")
        return 3
    denied = [p for p in candidates if not safe_path(p)]
    if denied:
        print("Denied changes outside approved inventory/test/docs scope:", *denied, sep="\n - ", file=sys.stderr)
        return 2
    for p in candidates:
        if pathlib.Path(p).is_symlink():
            print(f"Symlink not allowed: {p}", file=sys.stderr)
            return 2
    subprocess.check_call(["git", "add", "--", *candidates])
    subprocess.check_call(["git", "diff", "--cached", "--check"])
    if not command("git", "diff", "--cached", "--name-only"):
        return 3
    subprocess.check_call(["git", "diff", "--cached", "--binary", "--output=dev-agent.patch"])
    print(f"Validated {len(candidates)} changed paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
