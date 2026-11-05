# Dev Agent v2.5: UTC costs, settlement, and Codex authorization design

The combined inactive implementation and current rollout gates are documented
in [authenticated accounting](dev-agent-authenticated-accounting.md). The
following describes the earlier foundations and their historical limitations.

## Implemented in this PR (inactive)
- Manual protected `cost-audit` workflow reads **UTC midnight to observation time** project-level OpenAI Organization Costs API results. No Neon database secret enters the collector job. Its artifact is a **report, not an authenticated authorization token**.
- Pure settlement model distinguishes `reserved`, `started`, `failed_unreconciled` from `settled` and `cancelled_verified`. Only a verified transition can release a reservation. Failed jobs do not automatically release funds.
- Conservative budget assessment uses reported costs plus *outstanding* $5 reservations, avoiding counting previously verified settled reservations twice. Daily cap $10 and max 6 attempts; at $5 each, at most two pending reservations fit.
- Nine offline tests cover UTC-day boundary, empty delayed cost reporting, retry, stale data, failure, settlement, and cross-day behavior.

## Important: NOT YET WIRED TO LIVE CODEX
Existing `dev_agent_durable_controls.reserve()` still uses the old `reported_usd + reserved_usd` calculation and old DB states. The pure settlement model is **not a replacement for the database transaction**. Do not treat it as enforceable until a migration and transactional integration tests implement the same policy.

### Required next implementation
1. **Authenticated ingestion:** The Costs API collector and Neon writer must be separate jobs/environments. Do not download an arbitrary JSON artifact and trust its values. Bind collector run ID, project ID, UTC window and digest to a verified GitHub artifact attestation or equivalent signed statement, verify provenance in the DB writer, and reject missing/expired/ambiguous evidence. Keep the organization Admin Key out of the Neon job and the Neon URL out of the cost collector.
2. **Settlement migration:** Add explicit settlement state and proof metadata to the database; write a transactionally locked reconciliation procedure that releases only verified settled/cancelled reservations. Use a reporting-lag buffer and never interpret missing Costs API rows as proof of no charges. Run concurrent retry, failed run, and UTC rollover tests against real PostgreSQL.
3. **Execution permit:** An isolated, human-approved preflight job should atomically reserve in Neon and produce a signed, short-lived, single-use permit bound to `run_id`, `issue_number`, `head_sha`, `project_id`, expiry and nonce. The Codex job must verify this permit before the model step. Denial, missing evidence, stale evidence or replay must skip the Codex action entirely. The Codex job must not receive DB/admin credentials.
4. **GitHub control:** A separate workflow PR should make the preflight job a mandatory `needs` dependency and remove all paths that could invoke Codex without a verified permit. Keep manual dispatch and existing dual-label issue approval. Disable scheduled invocation. Do not allow any automated merge or production deployment.
5. **Live acceptance:** manual protected Costs API run, verified ingestion to Neon, real reservation, duplicate and stale denials, fail-closed no-secret/no-permit tests, real outbox notification and human review. Only then activate the gated workflow.

**Security note:** An artifact containing cost data is not itself proof of origin, and a successful CI run is not proof of real billing correctness. OpenAI Costs API reports may lag; $10 is an operational budget target, not a guaranteed hard API spending limit.

## Rollout status
No live Neon cost synchronization, reservation settlement, signed permits, Codex gating, schedule activation, merge, or production deployment occurs in this PR.
