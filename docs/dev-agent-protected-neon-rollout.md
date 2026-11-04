# Protected Neon verifier rollout — human approval required

New manual-only workflow: `.github/workflows/chubby-dev-agent-neon-trusted-permit-audit.yml`. It references environment `dev-agent-permit-verifier` (not the ordinary `dev-agent-control` environment), and invokes `dev_agent_trusted_verifier.verify_and_consume`, which checks HMAC, expiry, run/Issue/SHA/project bindings before calling the audited SECURITY DEFINER function. The verifier role must have EXECUTE but no direct INSERT on consumed_permit.

## Human setup, not performed
1. Review schema migration and database function independently; apply only to isolated Neon with a backup and audited owner. The existing CREATE TABLE IF NOT EXISTS will not upgrade existing constraints.
2. Provision Neon login `dev_agent_permit_verifier_login` with a strong random password and least privilege. Only USAGE on schema and EXECUTE on the reviewed function; no direct table write, CREATE, database ownership, or superuser.
3. Create GitHub Environment `dev-agent-permit-verifier`, restrict to main, add Required reviewers if supported, disable bypass. Configure secrets `DEV_AGENT_PERMIT_VERIFIER_DATABASE_URL`, `DEV_AGENT_PERMIT_HMAC_KEY`, and a short-lived `DEV_AGENT_TEST_SIGNED_PERMIT`; variables `DEV_AGENT_TEST_RUN_ID`, `DEV_AGENT_TEST_ISSUE`, `DEV_AGENT_TEST_SHA`, `DEV_AGENT_TEST_PROJECT`.
4. The test reservation must be created by a separate privileged fixture job for an isolated `proj_acceptance_` project. Never use a production project or grant the verifier INSERT on reservations.
5. The signed permit expires within 5 minutes. A manually stored secret may expire before approval. **The current workflow is not ready to run as a reliable end-to-end test until the fixture and permit are generated immediately before the verification step inside the protected trust boundary.** No secrets may enter the Codex job.
6. After this is fixed, run the workflow manually from main and inspect both success and fail-closed logs. The current rollback test is sequential within one transaction; concurrency on real Neon requires a separate isolation strategy that cleans up test rows safely.

No environment, role, key, schema migration or live Neon test was provisioned by this PR. Do not merge/activate until CI and independent review pass.
