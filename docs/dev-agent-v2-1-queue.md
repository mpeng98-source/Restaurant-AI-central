# Chubby Dev Agent v2.1 — autonomous task queue (first implementation slice)

This PR introduces a deterministic **read-only issue selector** and regression tests. It does not yet replace the v2 workflow's task selection, invoke Codex autonomously on new categories, or enable scheduling.

## Queue policy
- Issue must be open and have **both** `agent-approved` and `agent-safe` labels.
- `agent-blocked` or `agent-needs-human` rejects an issue.
- Existing open `Agent proposal: issue #N` prevents duplicate work.
- Oldest eligible issue wins, unless a specific approved issue is requested.
- Explicit high-risk keywords (database migrations, RLS, authorization, credentials, production deployment) fail closed pending human triage.
- Titles and bodies have strict size limits; this filter is a safety preflight, not a substitute for code review, permissions, or Codex sandboxing.
- GitHub Issue text is untrusted. A safe label must be applied by a trusted maintainer; do not give untrusted contributors label-management privileges.

## Local verification

```bash
python -m unittest discover -s scripts -p 'test_dev_agent_queue.py' -v
python -m py_compile scripts/dev_agent_queue.py scripts/test_dev_agent_queue.py
```

The existing CI security job now runs these tests. Actual hosted results must be inspected before merge.

## Next steps
1. Review queue logic and CI results.
2. Add a read-only GitHub API snapshot collector to supply Issues and open PRs as JSON to the selector; handle pagination and API errors fail closed.
3. Integrate the selector with v2 behind a default-off repository variable, while preserving existing manual `issue_number` behavior.
4. Run a manual no-model dry-run on an approved, safe Issue. Confirm no duplicate or unauthorized issue is selected.
5. Then test one bounded Codex run that opens a Draft PR, and measure API cost.
6. Only after multiple successful controlled runs consider scheduled mode. No autonomous merge or production deployment.

## Inventory project constraint
Sprint 2C PR #7 and Sprint 2D PR #9 involve RLS, migrations and approvals. Those remain human-supervised Codex work, not `agent-safe` queue tasks.
