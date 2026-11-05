# Chubby Dev Agent v2.4 — cost correlation and run governance

## Current implementation
This PR implements **pure, offline safety logic** only. It does not alter the Codex workflow or enable scheduled execution.

- Run correlation: associates a GitHub run ID, dedicated API project, start/end timestamps and two settled OpenAI Costs API observations. Reports the **project-wide reported cost delta** and explicitly marks exact per-run cost as unknown. Overlapping calls, reporting delay and unrelated project traffic prevent exact attribution.
- Quota preflight: counts reserved, started, completed and failed run records for the UTC calendar day; fails closed for stale cost observations, malformed/duplicate records, invalid estimates or exhausted limits. This is **not an atomic reservation** and must not be treated as enforcement in a concurrent workflow.
- Alerts: emits sanitized reason codes for CI failure, stale cost data, budget blocks and failed Codex runs. No actual notification transport is implemented.

## Required before unattended runs
1. **Dedicated project and usage telemetry:** move the Codex API key to the dedicated OpenAI project. Record the GitHub run ID, invocation start/end, model, token usage and request IDs from a trusted runner where available; do not claim request-level attribution from aggregate Costs API totals.
2. **Durable, atomic reservation:** use a transactionally locked database or equivalent strongly consistent store with a unique run ID and UTC day key; reserve before invoking Codex, including retries and concurrent runners. Never use a mutable JSON artifact as the authority.
3. **Fresh budget evidence:** read Costs API from the protected `cost-audit` environment, require fresh and complete observations, add a conservative allowance for delayed settlement, and enforce a separate API project spending threshold. The Costs API itself is not a real-time hard stop.
4. **Alerts:** use GitHub Issues or a scoped notification integration with deduplication, redaction and owner escalation. Never include raw CI logs, credentials, or sensitive prompts.
5. **Failure tests:** concurrent reservations, crash/retry, missing cost API, reporting lag, API rate limits, overlapping calls, and notification delivery failures.
6. **Human gates:** review CI and security; keep auto-merge, production deployment and schedules disabled.

## Verification
`python -m unittest discover -s scripts -p 'test_dev_agent_cost_controls.py' -v`

CI will run these tests; do not merge until they pass. No real API charges or live notifications are created by this PR.
