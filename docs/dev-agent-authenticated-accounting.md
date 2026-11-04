# Authenticated cost, settlement and single-use permit control plane

Issue #39 implementation, **inactive**. No Codex action, schedule, Neon
migration, role/secret provisioning, PR merge or deployment is included.
The ordinary Neon rollback acceptance on `cd389635` proves its write/denial
paths only; it does not prove this new trust chain or billing finality.

## Trust boundaries and commands

`scripts/dev_agent_accounting_cli.py` provides `collect`, `ingest`, `reserve`,
`consume`, and `settle`. It emits fixed sanitized status only. Connection URLs
and signing keys are environment secrets. JSON outputs are exclusive-create,
mode 0600. Input JSON is size-bounded and rejects duplicate keys. Failed
commands return 2; a result file or an exit code alone is never a Codex gate.

1. **Collector:** direct HTTPS to the fixed OpenAI Costs endpoint, no redirects,
   no database URL. Select one project and UTC day; validate buckets, pagination,
   USD, finite nonnegative amounts. Empty project rows mean unknown and deny
   collection. Explicit returned zero is reported evidence, never proof that
   nothing will be billed later. Round sub-micro-dollar totals UP, not down.
2. **Authenticated transport:** HMAC-SHA256 signs the report plus repository,
   workflow path, immutable source SHA, collector run ID/attempt and a maximum
   five-minute lifetime. The separate writer pins all expected values from
   trusted job context, not the report. A signature authenticates the protected
   collector, not OpenAI. Signing arbitrary uploaded reports is prohibited.
3. **Database writer:** only `ingest_cost` function access. It records a canonical
   signed-payload SHA-256 digest and producer metadata. Same-envelope retry is
   idempotent; same-window changed contents, time regression and lower reported
   totals fail closed. Raw unsigned legacy observations cannot authorize runs.
4. **Reserver:** only `reserve_run`; permit HMAC key, no Admin Key. Reservation
   and permit bind run ID, approved Issue, SHA and project. The caller must first
   perform the existing trusted Issue approval/scope checks. A key failure
   occurs before a reserve. Results are returned only after a committed top-level
   transaction. Lost output retains the reserve for reviewed cancellation.
5. **Verifier:** only `consume_permit`; separate credential and permit key, no
   direct table privileges. Python verifies the signature/bindings first; SQL
   rechecks database-time expiry and persisted SHA/Issue/project, locks the
   project, inserts unique nonce + run, and transitions reserved → started in one
   transaction. Concurrent/replayed/different-nonce attempts yield one success.
6. **Settlement reviewer/service:** separate review key and `finalize_run` role.
   No automatic proof signer is provided. Human-controlled reconciliation must
   independently check the protected execution records and billing evidence,
   record a review reference, and sign a `settlement_review_v1` envelope. A caller
   supplied `verified=true`, failed job, elapsed time, empty API result or project
   total alone cannot release money. Archive the signed review in protected
   audit storage under its reference; SQL stores its digest and reference.

The inactive manual workflow `chubby-dev-agent-authenticated-costs.yml` wires
collector → same-run artifact → writer with separate `cost-audit-v26` and
`cost-writer-v26` environments. It runs only on main after explicit activation
variable `DEV_AGENT_ACCOUNTING_V26_ENABLED=true`; this change does not set it.
Both jobs need the cost signing key; only the collector has `OPENAI_ADMIN_KEY`,
only the writer has `DEV_AGENT_COST_WRITER_DATABASE_URL`. Protect main-only
environment access, require review and prohibit bypass before activation.
Environment approval delays can expire the five-minute envelope: rerun the
whole collector/writer chain with a new attempt, do not extend or re-sign an
old report. Download is exact artifact name from the same run and attempt.

## Transactional accounting

`ops/migrations/0001_dev_agent_accounting.sql` is a versioned **separate schema**
in the isolated Dev Agent database. It does not rewrite restaurant migrations
or the existing Neon control schema. Projects default disabled. Per-project
transaction advisory locks serialize every mutation, including across UTC days.

Policy is 6 attempts per UTC day, $10 operational exposure estimate, $5 per
outstanding run. Exposure is current-day reported cost + ALL outstanding
reservations, including previous days, + the candidate $5 reserve. Cancelled
attempts still count toward six. Failed runs remain reserved until reviewed;
the failure role may only mark started → failed_unreconciled. Already-finalized
reservations do not add another $5. Do not claim exact per-run cost or a hard
API spending cap from delayed project totals.

Cancellation requires a signed never-started review, reserved state and no
consumed permit. Settlement requires started/failed state, a consumed permit,
cost evidence for the reservation's UTC day covering its completion (or that
day's end for a cross-day run), a minimum 24-hour review buffer, and separately
signed billing-finality review. The buffer alone proves no finality. Final
states are terminal; concurrent retry cannot release the same reserve twice.
Daily cumulative costs are never allocated as exact individual run charges.

Settlement payload fields: `kind=settlement_review_v1`, `producer` (repository,
workflow, SHA, run_id, attempt), issued/expiry seconds, `binding` (run_id,
issue_number, head_sha, project_id), `decision`, `cost_digest`, `finished_at`,
`review_reference`, plus **either** `billing_finality_reviewed=true` for settled
or `never_started_reviewed=true` for cancelled_verified. A distinct protected
review key signs this payload using `dev_agent_signed_evidence.sign`; it must
never be accessible to the collector, reserver, verifier or Codex jobs.

## Migration and least-privilege rollout (NOT performed)

The one-shot migration deliberately fails if the new schema already exists.
Test in an isolated database; take a reviewed backup before any live apply.
Transfer schema, tables and SECURITY DEFINER functions to a dedicated restricted
NOLOGIN owner; verify fixed `pg_catalog, pg_temp` search paths. PUBLIC has no
schema, table or function access. Grant each dedicated protected LOGIN role
schema USAGE and EXECUTE on its **one** function only (cost writer, reserver,
verifier, settlement, failure recorder); no role receives table access. The
verifier for this schema is not the current live read-only verifier identity.

There is intentionally no automatic import from the old control plane. Before
cutover, stop the old runner, reconcile/migrate every unresolved old reservation
and outstanding attempt count, and prove no other workflow can bypass this
schema. Starting a fresh project row while old reservations exist is forbidden.
Do not enable the new workflow until independent review approves migration,
owner/grants, protected main source, key separation, legacy reconciliation and
actual protected live acceptance. The existing v2/v2.1 Codex workflows remain
unchanged and are not protected by this new code until separately integrated.

## Verification

`test_dev_agent_cost_evidence.py` exercises tampering, producer/SHA/run/attempt
binding, time windows, precision, pagination, missing costs and review proof
denial before SQL. `test_dev_agent_accounting_cli.py` covers safe transport and
failure output. `test_dev_agent_accounting_postgres.py` creates a fresh database,
restricted NOLOGIN function-owner/service roles and ephemeral test keys; it
tests concurrent reserve/consume/cancel, failure, replay, stale evidence,
cross-day exposure, settlement and rollback with independent connections.
SET ROLE in disposable PostgreSQL proves role grants, not live login secrets.

The acceptance workflow uses PostgreSQL 16 and no protected secrets; skipped
database tests fail the job. Local execution requires
`DEV_AGENT_DISPOSABLE_TESTS=1` and a loopback `DEV_AGENT_TEST_DATABASE_URL`; remote
URLs are refused. It creates/drops only a random acceptance database/roles.
No test modifies Neon. Protected live cost collection, settlement reviews,
Neon grant verification and Codex gate activation remain separate rollout gates.

Costs API reference: https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/costs
