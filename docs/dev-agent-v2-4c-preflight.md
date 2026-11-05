# Issue #33 — controlled Codex preflight integration

This PR is the **first, inactive integration slice**. It introduces a CLI that atomically reserves a quota in a dedicated PostgreSQL control-plane DB. It does not change `.github/workflows/chubby-dev-agent-v2-1.yml`, does not provision a database or grant secrets, and does not enable schedules.

## Policy
Daily maximum: 6 attempts; daily budget: $10; reserve $5/run. At most two reservations/day are possible under an empty ledger. Cost evidence must be fresh and from a trusted UTC-day collector. If the DB, credential or cost evidence is absent, the CLI refuses to issue a permit.

## Blocking gaps before wiring Codex
1. Provision a dedicated control-plane database with a least-privilege role; keep its credential in a protected GitHub Environment with manual reviewers. Do not place it in the Codex job.
2. Fix the budget accounting lifecycle: `reported_usd + reserved_usd` can double-count previously settled reservations. Define and test reservation settlement/release, delayed cost updates and crash recovery before considering this a trustworthy financial gate.
3. A GitHub Actions job cannot automatically transfer an environment approval to a different job. Design an auditable, short-lived permit bound to run ID, issue ID and SHA, and verify it **inside** the Codex job before any model invocation. Ensure a manual dispatch cannot bypass it.
4. Implement trusted UTC-midnight-to-now Costs API collection; the existing rolling-24-hour audit must not be used as daily budget evidence.
5. Run real PostgreSQL concurrency, stale-cost, no-secret, permission-denied, day rollover, and manual approval tests. Review whether GitHub-hosted runner networking can reach the isolated database without public exposure.
6. Test alert-outbox delivery with a restricted GitHub token and reconcile the `sending` state after failures.
7. Only then create a separate PR wiring the controlled jobs into the v2.1 Codex workflow. Keep scheduled runs, automatic merge and production deployment disabled.

## Tests
`python -m unittest discover -s scripts -p 'test_dev_agent_preflight.py' -v`

No live database is created and no API admin key is used by this PR.
