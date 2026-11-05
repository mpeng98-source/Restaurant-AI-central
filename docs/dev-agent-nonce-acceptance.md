# PR #40 nonce replay acceptance

Ephemeral PostgreSQL CI tests 12 concurrent consumers of the same nonce, committed replay, distinct nonces, rollback and invalid nonce. A pass demonstrates uniqueness in CI, not production enforcement.

The manual protected Neon audit checks whether the separately provisioned consumed_permit table exists and can be read by dev_agent_runner. It is read-only. Do not apply the draft DDL to Neon without independent DBA review, backup, and dedicated verifier role.

Blocking items: real Neon concurrent consumption with a least-privilege verifier role; key isolation; authenticated cost provenance; atomic reservation and one-use permit validation before Codex. The signed envelope is replayable without the DB ledger. No changes to active Codex workflow, schedules, auto-merge or deployment.


## Independent migration and permissions review — findings

**Do not apply draft SQL to Neon yet.** Current draft only constrains nonce length, SHA length, and the nonce primary key. It does not enforce hexadecimal nonce/SHA formatting, uniqueness of (run_id, issue_number, head_sha, project_id), expiry, permit signature validity, or a foreign-key binding to a previously approved reservation. A different nonce could authorize the same run twice unless another trusted control prevents it. These are security blockers before live consumption.

**Dedicated verifier role:** create `dev_agent_permit_verifier` separate from `dev_agent_runner`, Codex, and the restaurant API. Do not grant schema CREATE, database ownership, BYPASSRLS, or blanket UPDATE. Prefer a narrow audited SECURITY DEFINER function that atomically checks run binding, signature/provenance, expiry, and reservation state, and inserts a consumed nonce. Grant only EXECUTE to the verifier role. The existing `dev_agent_runner` role should not receive direct write privileges on `consumed_permit`.

**Environment:** the future verifier workflow must use a separate `dev-agent-permit-verifier` GitHub Environment, allow only `main`, and require independent approval where the repository plan supports it. GitHub's environment settings must be checked directly before any secret is added. Never copy a signing key or verifier database URL into the Codex job.

**Acceptance before merge/activation:** after the revised schema, database role, and audited function are reviewed, run isolated PostgreSQL tests for duplicate nonce and duplicate run, concurrent consumption, expired/tampered permits, wrong SHA/Issue/project, and crash/rollback. Then run a separately approved, rollback-only Neon test. A read-only Neon ledger audit does not validate these write paths.


## New hardening changes
- The revised CREATE TABLE draft enforces hex nonce/SHA, valid project format, and a UNIQUE(run_id) constraint. If the table already exists, an audited ALTER migration is required; CREATE TABLE IF NOT EXISTS does not upgrade existing constraints.
- The verifier-role draft deliberately creates only a NOLOGIN role and grants no direct table writes. Provisioning a login, an audited SECURITY DEFINER function, and a narrowly scoped EXECUTE grant remain separate human-approved steps.
- A rollback-only Neon write acceptance script is staged but **must not be run** until that audited function/role is implemented; direct INSERT privileges would violate the intended least-privilege design. The script is not wired to a workflow.
- Ephemeral PostgreSQL CI is the only concurrency test currently executable. Real Neon concurrent replay protection remains unverified.
