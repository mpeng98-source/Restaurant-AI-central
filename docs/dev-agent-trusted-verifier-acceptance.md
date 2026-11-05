# Trusted permit verifier — staged acceptance, NOT live

The new `scripts/dev_agent_trusted_verifier.py` function verifies HMAC signature, binding to GitHub run/Issue/SHA/project, issue/expiry/nonce, then calls a parameterized SECURITY DEFINER function to atomically consume the nonce. All signature checks happen before any SQL write.

The CI suite adds seven offline negative tests and four real **ephemeral PostgreSQL** integration tests, including eight simultaneous consumers, different nonce/same run, expired and tampered signatures, and denied direct table insertion. CI uses an ephemeral test-only signing key and a NOLOGIN role activated via SET ROLE by the CI superuser. These are **not** production credential proofs.

## Mandatory gates before protected Neon
1. Independently review and apply the revised ledger DDL and function to the isolated control database. Verify owner is a restricted non-login owner, search_path is fixed, PUBLIC EXECUTE revoked, and the existing table has the new constraints (CREATE TABLE IF NOT EXISTS does not migrate existing tables).
2. Provision a dedicated LOGIN role via Neon with a random secret, no CREATE, no direct INSERT/UPDATE/DELETE on ledger, and EXECUTE on the function only. Protect its URL in a separate main-only GitHub Environment with required human approval if available. Never use the existing dev_agent_runner account.
3. Provide a separate HMAC key accessible **only** to the protected verifier. The Codex job must not receive the key or DB URL. Verify the role's effective privileges from an actual connection.
4. A database function callable by the verifier role still does not cryptographically verify signatures itself. The service must be the sole holder of verifier credentials, and its invocation must be controlled; no arbitrary caller should be able to supply unsigned inputs to that privileged function.
5. Implement a protected, manual, rollback-only Neon integration workflow after approval. It must verify signature/expiry/replay and concurrent calls, and prove zero persistent test rows. Do not create a fake success result or silently substitute CI for Neon.
6. Confirm settlement and trusted Costs API ingestion separately before activating Codex.

The active Codex workflow is unchanged. No Neon migration, live tests, scheduled execution, auto-merge, or production deployment were performed.
