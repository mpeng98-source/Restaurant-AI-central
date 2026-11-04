# Protected manual coding agent — implementation and rollout

This increment connects Issue approval, authenticated costs, transactionally
bound reservations and single-use permits to the model entrypoint. The
activation variable remains unset. Existing ungated v1/v2/v2.1 entrypoints are
retired in this change; none can invoke a model after merge. There is no schedule,
automatic merge, deployment or automatic release of reserved funds.

## Execution chain

The only model action is in `chubby-dev-agent-gated.yml`. Its dependency chain:

```
human approval -> select approved safe Issue -> read-only readiness audit
 -> protected cost collector -> authenticated ingestion -> atomic reservation
 -> signature verification + committed one-use consumption -> model admission
 -> isolated model proposal -> fresh-checkout validation -> Draft PR
```

All jobs check out the dispatch's immutable SHA, never a moving branch. The
control CLI requires the exact repository/workflow/main event identity. Issue
selection, reservation, verification and model admission reject removed labels,
edited task content or an existing proposal. A SHA-256 task digest and run
attempt bind the snapshot to both the reservation row and permit. Re-running
any job invalidates prior attempt outputs; it cannot reuse a consumed permit.

Only trusted `needs.authorize.outputs` may transport the admission decision.
Neither user input nor an arbitrary artifact can set it. The generator requires
authorize success and a matching receipt. Admission expires five minutes after
consumption and is rechecked after model-environment approval and fresh Issue
checks, immediately before the action. This is **job admission**, not a hard
inference timeout: action setup/model work can continue after admission. The
database has already charged the run as started; its $5 reserve remains held.

The model action is the last step of its job, with `drop-sudo` and `:workspace`.
No DB URL, HMAC/signing/Admin Key or PR write token is available to that runner.
Its filesystem is discarded. It returns bounded JSON with existing file paths
and complete replacement text. A separate fresh runner validates paths, file
count/size and symlinks, then uses create-only GitHub APIs to publish a Draft PR.
The publisher never executes model-supplied code/tests and never merges. Only
existing tests and Sprint 2 docs are allowed for this pilot. CI and human review
are still required; a model's text is not proof of successful tests.

Failure/cancellation retains the reservation. The failure role may mark an
already-started run `failed_unreconciled`, never release funds. A separately
reviewed signed settlement/cancellation is still required as described in
[authenticated accounting](dev-agent-authenticated-accounting.md).

## Neon rollout plan (review before applying)

Known target: project `chubby-dev-agent-control` (`super-pond-95165425`), branch
`production` (`br-super-glade-arow66co`), database `dev_agent_control_db`. This is
the isolated agent control database, not the restaurant application database.
Read-only inspection before this change found no old reservations or attempts
for the current UTC day, and the new accounting schema was absent. This is a
point-in-time observation, not a perpetual readiness claim.

1. Prepare a temporary Neon migration branch/copy and retain its migration ID.
   Apply **0001**, **0002**, then `ops/dev-agent-v27-provision-review.sql` there.
   These add only `dev_agent_accounting` and dedicated v27 roles. No password,
   project activation or GitHub variable is embedded in SQL.
2. Test on that branch: restricted owner attributes/search path, PUBLIC revoked,
   exact per-function grants, no direct table access, raw legacy reserve/consume
   denied, task/attempt mismatch, one-use/replay, rollback and empty legacy state.
   A `SET ROLE` test proves grants, not actual LOGIN/password authentication.
3. Obtain explicit approval to apply the reviewed migration to the target branch.
   The Neon migration tool requires confirmation before completing the migration.
   Do not apply by an alternate SQL route to bypass that confirmation.
4. Provision distinct strong passwords through a protected channel and verify
   actual logins. Never use Neon's default admin-role creation option for service
   identities (it inherits neon_superuser). The review SQL creates restricted SQL
   roles directly; Codex must never receive an owner/service credential.
5. Before activating, re-run the read-only audit; old pending reservations,
   old attempts today, unbound new reservations, extra function grants, unsafe
   owner attributes or disabled projects all deny. Reconcile legacy state rather
   than dropping it. Any missing schema/permission fails closed.

## GitHub protected environments

Restrict every environment below to main. Require human approval for the run
approval environment; protect credential environments against bypass and
unreviewed source access. Configure these exact secrets in their own environments:

| Environment | Secret(s) | SQL role/function |
|---|---|---|
| `dev-agent-run-approval-v27` | none | human run approval |
| `dev-agent-control-audit-v27` | `DEV_AGENT_AUDIT_DATABASE_URL` | `dev_agent_auditor_v27` / rollout_status |
| existing `cost-audit` | existing `OPENAI_ADMIN_KEY`, new `DEV_AGENT_COST_SIGNING_KEY` | collector, no DB URL |
| `cost-writer-v27` | `DEV_AGENT_COST_WRITER_DATABASE_URL`, `DEV_AGENT_COST_SIGNING_KEY` | dev_agent_cost_writer_v27 / ingest_cost |
| `dev-agent-reserver-v27` | `DEV_AGENT_RESERVER_DATABASE_URL`, `DEV_AGENT_PERMIT_HMAC_KEY` | dev_agent_reserver_v27 / reserve_task |
| `dev-agent-verifier-v27` | `DEV_AGENT_VERIFIER_DATABASE_URL`, `DEV_AGENT_PERMIT_HMAC_KEY` | dev_agent_verifier_v27 / authorize_task |
| `dev-agent-codex-v27` | dedicated-project `OPENAI_API_KEY` | model only |
| `dev-agent-publisher-v27` | scoped `CHUBBY_DEV_AGENT_PR_TOKEN` | repository Contents + PR write only |
| `dev-agent-failure-v27` | `DEV_AGENT_FAILURE_DATABASE_URL` | dev_agent_failure_v27 / mark_failed |

Settlement uses its separate review key and settler credential; neither enters
this workflow. Reuse identical cost signing keys only between collector/writer,
and identical permit keys only between reserver/verifier. Keep the key classes
distinct. Never copy an organization Admin Key into model or writer environments.
The existing `cost-audit` environment already has the protected Admin Key and
is reused without extracting/replacing that key. Existing repository
`OPENAI_API_KEY` and `CHUBBY_DEV_AGENT_PR_TOKEN` can be referenced only in their
respective gated model/publisher jobs; their values cannot be read back or
copied. New DB/HMAC credentials still require protected environment setup.

Set the dedicated `CHUBBY_DEV_AGENT_PROJECT_ID` repository variable. After all
reviews and actual credentials pass, explicitly enable
`CHUBBY_DEV_AGENT_GATED_ENABLED=true` for the one manual pilot, and turn it off
again after that attempt. This variable enables manual dispatch, not a schedule.
Approval delays can expire cost evidence/permit/receipt; deny and review the
held reservation rather than extending old evidence or bypassing the gate.

## One small real canary

Use a single approved `agent-safe` + `agent-approved` Issue asking for a small
clarification of the existing `docs/sprint-2b-counting.md` worked example:
0.315 kg = 315 g; expected 340 g gives -25 g variance, and submission does not
post a stock movement. No new functionality, executable code or broad edits.
Do not label it approved until the old entries are retired on main.

Dispatch the new workflow once from main with that exact Issue number. Confirm
the observed SHA/attempt, trusted costs, one $5 reserve, exactly one consumption,
one model invocation and one Draft PR. Review the generated diff and hosted CI.
Keep all proposed merges/deployments manual. Record failure if appropriate and
settle only after independently reviewed billing finality; a delayed/empty cost
response is not zero-charge proof. Existing six-attempt/$10 estimate policy
remains conservative and is not a hard OpenAI billing cap.

## Recorded Neon temporary-branch rehearsal

Migration `e8e30cc8-0734-4042-a6b3-39a9ba2dae80` was prepared on temporary branch
`br-withered-sea-aremunu3`, parent `br-super-glade-arow66co`. The decoded reviewed
SQL SHA-256 is `01af4eab4987956ebf06dfe7610ae8eb3bacf725dc9c87adaacec8167e7e37f9`.
`dev_agent_migration_bundle.py` transports the three SQL files as one atomic DO
statement because the migration tool splits ordinary function bodies on raw
semicolons. It does not hide additional SQL; decoding reproduces those files
minus outer BEGIN/COMMIT markers. A non-superuser local migration test also
verifies this path and the temporary ownership-transfer grants.

On the Neon temporary branch: all seven v27 role attribute sets are restricted,
the owner is NOLOGIN, no role inherits neon_superuser, eight functions use the
restricted owner and fixed search path, and raw reserve/consume grants are
denied. A rollback-only synthetic probe used temporary SET ROLE fixture access:
cost ingestion and reservation true; wrong attempt false; first consumption
true; replay false; direct INSERT privilege false. Independent post-rollback
queries returned zero project, cost, reservation and permit test rows.
This is SQL/role rehearsal, not a real password login, live OpenAI cost source,
production migration or paid model invocation. Completion still requires explicit
approval and actual protected configuration. The parent branch was not migrated.

## Evidence and limits

CI runs the whole chain against disposable PostgreSQL 16 with an explicit fake
model callback and ephemeral keys. It tests denial before execution, concurrent
consumption, replay, edits/revocation, attempt binding, failure retention,
least-privilege provision script and readiness audit. It never calls OpenAI or
Neon. A passing fake-model test does not establish live billing or login proofs.

OpenAI's action security guidance recommends separate publication and a final
model step with privilege isolation:
https://learn.chatgpt.com/docs/github-action#security-checklist

## Cost collection diagnostics

The first protected canary, run `41778397704` on main commit
`a0d252b56583e86377cbeb96adf035fb26a9648e`, stopped in `collect` with the old
generic denial. Selection and the Neon read-only audit passed. No model or
publisher ran, and a subsequent read-only database check found zero cost
evidence, reservations, permits, settlements, and legacy reservations. The
repository activation variable was returned to `false`. The old log does not
establish the underlying cause.

`Dev Agent cost diagnostic (read-only, manual)` runs only on `main`, requires the
existing `cost-audit` environment approval, and uses the same fixed-endpoint
collector and current UTC-day validation. It has no signing, database, model,
or PR credential. It emits no report artifact or execution evidence and cannot
authorize the coding workflow. It does not change the activation variable.

Collection failures now print one constant reason code, without exception
messages, response bodies, URLs, headers, or credentials:

| Code | Meaning and next check |
| --- | --- |
| `COST_CONTEXT_INVALID` | The protected repository/workflow/main context did not validate. |
| `COST_CONFIGURATION_MISSING` | Required collector configuration is missing or diagnostic output was requested. |
| `COST_API_HTTP_400` | API rejected the request; inspect the official parameter schema before changing collection. |
| `COST_API_HTTP_401` / `COST_API_HTTP_403` | API authentication or authorization was rejected; check the protected Admin Key configuration. |
| `COST_API_HTTP_429` / `COST_API_HTTP_OTHER` | API rate limit or another HTTP failure; no evidence was accepted. |
| `COST_API_TRANSPORT` | Connection or timeout failure. |
| `COST_PROJECT_COSTS_UNKNOWN` | No project cost rows were returned; this remains unknown spend and must never be treated as zero. |
| `COST_RESPONSE_INVALID` | JSON, bucket, currency, project, amount, pagination, or another response check failed. |
| `COST_SIGNING_DENIED` / `COST_OUTPUT_DENIED` | Signing configuration or exclusive evidence-file creation failed. |

After review and merge, run this diagnostic once to obtain the actual category.
Keep the coding activation variable `false`; a diagnostic success alone does
not complete the real model canary or authorize another model attempt. Do not
relax missing-cost checks, synthesize a zero report, or replay expired evidence.

