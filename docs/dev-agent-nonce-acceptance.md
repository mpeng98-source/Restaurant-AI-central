# PR #40 nonce replay acceptance

Ephemeral PostgreSQL CI tests 12 concurrent consumers of the same nonce, committed replay, distinct nonces, rollback and invalid nonce. A pass demonstrates uniqueness in CI, not production enforcement.

The manual protected Neon audit checks whether the separately provisioned consumed_permit table exists and can be read by dev_agent_runner. It is read-only. Do not apply the draft DDL to Neon without independent DBA review, backup, and dedicated verifier role.

Blocking items: real Neon concurrent consumption with a least-privilege verifier role; key isolation; authenticated cost provenance; atomic reservation and one-use permit validation before Codex. The signed envelope is replayable without the DB ledger. No changes to active Codex workflow, schedules, auto-merge or deployment.
