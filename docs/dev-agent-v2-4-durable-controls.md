# Chubby Dev Agent v2.4 — durable controls implementation (review only)

## Owner-selected policy
- Maximum daily attempts: **6**, UTC day.
- Daily project budget ceiling: **$10**.
- Conservative reservation per Codex run: **$5**.
- **Effective budget capacity: at most 2 runs per day** when no other reported charges exist. Six is a ceiling, not a promise that six can run. With $5 reservations, the $10 budget is the binding constraint.

## Implementation
- `ops/dev-agent-control-schema.sql`: isolated PostgreSQL control-plane schema. This is **not applied** by the restaurant Alembic migrations. No restaurant tenant role or Codex credential should have access.
- `scripts/dev_agent_durable_controls.py`: transactionally locks one project/day row with `SELECT FOR UPDATE`, rejects stale costs, records reservations keyed by run ID and project/day/Issue, stores trusted run telemetry and daily cost observations, and queues deduplicated alerts.
- The alert delivery function uses `gh issue create` with sanitized codes and run IDs. It is **implemented but has not sent a live notification**. Delivery requires a separate GitHub credential with Issues write permission. Failed deliveries remain in `sending` state for manual reconciliation to prevent duplicate issue spam.
- Cost reconciliation in `scripts/dev_agent_cost_controls.py` remains project-level window delta, never an exact per-run charge.
- All scripts are **not wired into the live Codex workflow**. Scheduled runs stay disabled.

## Safety/operational gaps before enabling
1. Independent DBA review and apply isolated schema to a dedicated PostgreSQL database. Set up a least-privilege role and a dedicated secret accessible only to a controlled preflight workflow, never Codex.
2. Real PostgreSQL concurrency integration tests (simultaneous reservations, crash/retry, unique Issue collisions, UTC rollover). Mock-based unit tests alone are insufficient.
3. Trusted collector must write cost observations for the **current UTC day from midnight**. The existing 24-hour rolling cost audit is **not** a valid input for the UTC daily budget. Require fresh data and an allowance for OpenAI reporting lag; API project spend limits/alerts are a separate backstop.
4. Introduce reservation release/settlement policy. Current conservative reserved funds are never released, including failed runs, until a separately reviewed accounting procedure is implemented.
5. Integrate post-Codex telemetry from a trusted runner. Record request IDs and usage when available, without placing sensitive output or keys in alerts.
6. Add actual alert sender integration tests using an authorized bot token, redaction checks and manual reconciliation of `sending` records.
7. Verify protected `cost-audit` Environment approvals and remove repository-wide Admin Key copies.

## Test
`python -m unittest discover -s scripts -p 'test_dev_agent_durable_controls.py' -v`

Do not merge or deploy without hosted CI and human review. No automatic scheduling, merge, or production deployment.

## Additional acceptance evidence
- Real PostgreSQL integration test added: `scripts/test_dev_agent_postgres_integration.py`. The CI verify job now requires this against PostgreSQL 16, including concurrent reservations, same-run retries, and same-Issue collisions. The updated CI result must be checked before approval.
- GitHub connector alert smoke test created Issue #32 and closed it. This verifies the connected GitHub integration can create an Issue, **not** the database outbox's `gh issue create` sender, which still needs a separate authorized live test.
- The budget SQL is not deployed or connected to the v2.1 Codex job. Protect the dedicated control-plane credential with a human-reviewed Environment. Do not add a direct DB secret to the Codex execution step.
- Before wiring the official workflow: require an independent security review of SQL privileges, a fresh UTC-day cost collector, and a controlled preflight that **fails closed** when database, cost data, or approval is unavailable. Preserve existing Draft PR and no-deploy restrictions.
