# Issue #39 — signed evidence and permit foundation

This is an inactive, stacked implementation on PR #38. No change to the live Codex workflow.

## Implemented
- HMAC-SHA256 envelope with 5-minute maximum validity, bound to GitHub run ID, Issue number, commit SHA, project ID and nonce.
- Constant-time signature comparison; tampering, wrong run/SHA, expiration and weak keys rejected.
- PostgreSQL unique nonce-consumption helper and review-only schema draft.
- Unit tests explicitly demonstrate that signature verification **alone is replayable**; the database nonce ledger is mandatory.

## Security blockers
1. The HMAC signing key cannot be available to the Codex job. An isolated verifier job must verify the permit, consume its nonce in a transaction, and emit a short-lived authorization decision bound to the same run and SHA. This decision must be enforced by the workflow before Codex and cannot be spoofed by untrusted artifacts.
2. The current nonce ledger is not applied to Neon and lacks a live concurrency acceptance test. It is not yet single-use in production.
3. Costs API provenance is not authenticated. Do not use unsigned cost artifacts as authorization evidence. Keep OPENAI_ADMIN_KEY and DEV_AGENT_CONTROL_DATABASE_URL in distinct protected environments.
4. Settlement migration remains a draft; the existing database reserve function is not yet reconciled with the new settlement policy.
5. Do not wire the existing v2.1 workflow until a separate protected job validates the complete chain (approved Issue → trusted cost evidence → atomic reservation → signed decision → one-time consumption) and tests denial for missing credentials, stale costs, duplicate runs, replay and job failure.
6. No scheduled runs, automatic merges or production deployments.

This PR does not sign a live permit, access protected secrets, write Neon, or call Codex.
