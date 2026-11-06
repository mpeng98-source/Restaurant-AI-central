# Exact issue-58 exception review package

Base main: db28f8cd1005e4376a46cb27775fc0fffcbaa216. All files below are local,
inactive review material. The workflow patch applies to the approved base file;
it has not been applied to a live workflow or pushed.

## Candidate inventory

- experiments/first_run_accounting/workflow.patch: exact unified workflow diff.
- experiments/first_run_accounting/workflow.candidate.yml: complete resulting YAML.
- exception.sql and exception_grants.sql: schema/functions, a replacement of
  normal reserve_run adding the shared-lock exception guard, and separate restricted
  grants. No roles, credentials, policy insertion or enable statement.
- exception_runner.py: claim consumption in the protected verifier job, followed
  by trusted job outputs. No model key and no provider invocation in that job.
- exception_audit.py: read-only extension to the unchanged normal auditor.
- artifact.py: exact-field, bounded, context-validated sanitized metadata writer.
- postgres_acceptance.py: real restricted-role PostgreSQL test harness.
- test_artifact_workflow.py and test_exception_runner.py: failure and boundary tests.
- test_expressions.mjs: seven assertions using pinned official expression evaluator.
- cost_bound.py: conservative pricing arithmetic only; no network or admission.

For a release branch, copy those runtime modules from this review revision,
apply workflow.patch to the stated base, and update the existing workflow tests
to reflect the explicit exception. Do not copy the older offline branch wholesale.
No automated policy seeding is included. The operator must bind the new reviewed
release SHA, fresh attempt-1 run ID, issue-58 task and fixed request hashes and
approval record into the singleton row after separate action-time approval.

## What the workflow changes

The new unknown_cost_exception boolean defaults false. True requires issue 58
and the existing scoped_canary input, main ref, enabled flag and attempt 1.
All existing protected environments remain in the dependency chain. For this
explicit exception, collect/ingest/reserve execute disclosure barriers rather
than fabricating a cost envelope or normal reservation. The verifier consumes
the exact-run database claim and emits the ordinary-shaped admission receipt.
This is the intentional security-policy exception being reviewed.

The generator keeps its current API key alone, existing admission/freshness
checks, fixed prompt/model, single request, network-isolated arithmetic worker
and disabled publication. Exception metadata is retained in the verifier and
generator artifacts for seven days. Upload actions use exact file paths and
always conditions; host loss can still lose artifacts. The database claim
persists even if outputs/upload fail. No timeout or artifact failure refunds it.

False preserves normal collection/reservation/authorization and its fail-closed
empty-cost behavior. General coding remains held. No additional spend approval
is sought; the exact exception/grant/policy changes still need security review
and action-time authorization before installation or merge.

## Request-cost analysis (official sources checked 2026-11-06)

The [GPT-6 Luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna)
lists a 1,050,000-token context, USD 0.10 input, 0.125 cache-write and 0.50 output
per million tokens. Large prompts have 2x input/cache and 1.5x output pricing;
regional processing can add 10%. The request selects default service tier,
reasoning none, no tools, no background/streaming/history, and 1024 output tokens.

Conservatively charging the *entire context* at both ordinary input and cache-write
rates (intentional overcount), with large-prompt multipliers and regional premium:

`(1,050,000 / 1e6 * (0.10 + 0.125) * 2 + 1024 / 1e6 * 0.50 * 1.5) * 1.10`

= USD 0.5205948, rounded upward to USD 0.520595. The proposed USD 5 incremental
reservation is above this documented-price scenario. It is not a provider-side
dollar limit. This calculation deliberately does not assume the response-side
4096-input-token check can prevent a charge; that check runs after inference.

Limitations: model alias/pricing can change; account-specific terms, taxes,
infrastructure, existing usage and concurrent callers are not bounded by this
arithmetic. Account model entitlement has not been tested by an API request.
The [official reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)
documents max_output_tokens as bounding generated reasoning, visible and formatting
tokens together. The calculation assumes the provider honors that request limit.
No paid token-count/inference probe was made. Revalidate terms before activation.
Unknown prior costs remain unknown, so an all-in USD 5,000 daily bound cannot be
claimed. California reset remains the user's ceiling convention; the normal
collector still uses UTC-day evidence and is not rewritten by this exception.

## Validation and remaining review

Twenty-one disposable PostgreSQL tests pass, including the unchanged full auditor
with all normal grants plus the proposed exception grant. Negative ACL cases
cover unrelated-role table/column access, PUBLIC access, schema CREATE, and
verifier schema USAGE/function EXECUTE WITH GRANT OPTION. Both normal/exception
admission orderings, concurrent admission (exactly one winner), restart,
disconnect, rollback, expiry, NULL/changed bindings and stop behavior pass.
Nineteen offline unit/workflow/artifact tests pass. Seven expression assertions
pass using @actions/expressions 0.3.25 and Node 24.22.1: the original empty receipt
throws, the revised empty/missing receipt parses safely, valid digest survives,
malformed nonempty receipt throws, and the reserve condition switches correctly.
The evaluator's extensionless imports require a test-only Node resolver hook;
its source/semantics are unchanged. Reproduction is in test_expressions.mjs.
The workflow parses as YAML; git apply --check passes on the base.

This does not simulate the GitHub service scheduler, protected-environment UI,
artifact backend, or actual provider. No actionlint binary was available. An
independent review must inspect the whole workflow/receipt trust chain and the
remaining policy risks before activation. Ordinary accounting does not include the exception in totals. Instead, the
normal reserve_run function (also called by reserve_task) now checks the claim
under the same transaction advisory lock and denies every subsequent reservation
for that project, across days and callers. No reconciliation/release function is
provided. Services cannot delete/rearm the claim. General coding remains held
until separately reviewed reconciliation. Owner/superuser administrative writes
remain a trusted boundary; this is not a defense against a database administrator.

Action-time approval targets: exact PR/merge; install schema and replace the normal reserve_run function with the reviewed
shared-lock guard; grant USAGE plus
EXECUTE only to existing dev_agent_verifier_v27 in dev_agent_control_db; insert
one immutable-to-service-role policy for the reviewed run; and perform that one
run with prior exposure unknown. No credential move/create or protection change
is required in the revised design. An expired consumed claim is not rearmed.


## Isolation follow-up

The ed0ff693 candidate was vulnerable to REPEATABLE READ transaction snapshots.
Reproduced independently in both directions: a restricted caller established a
snapshot, the competing admission committed, then the stale caller acquired the
shared advisory lock and still admitted. Both persisted rows (one normal and one
exception) were present. The lock alone did not refresh a transaction snapshot.

Both consume and reserve_run now return false unless transaction_isolation is
exactly read committed, before taking the lock or reading admission state. This
also covers reserve_task, which delegates to reserve_run. REPEATABLE READ,
SERIALIZABLE and READ UNCOMMITTED are deliberately unsupported; no isolation
setting is silently changed. Existing autocommit callers use READ COMMITTED.

Regression tests establish stale snapshots before the opposing commit in both
directions; test fresh admissions under all three unsupported levels; and force
both READ COMMITTED lock orders with an observed advisory wait before the winner
commits. These tests verify that subsequent function queries see that commit.
The original concurrency, restart, restricted-role and auditor tests remain.
No isolation test uses live infrastructure or provider requests.

Expiry remains consumption-time policy validation, followed by a separate
300-second receipt created after commit, not capped at policy valid_until. The
claim persists indefinitely and blocks normal admissions even after expiry or
midnight. Neither commit-time expiry nor a provider-call deadline tied to policy
valid_until is implemented. Reconciliation and activation still require review.


## Release integration

This release copies the reviewed runtime and SQL byte-for-byte from 270f7cd1498b9b75c8a9fedb1888366c41e78dc3
onto main db28f8cd1005e4376a46cb27775fc0fffcbaa216 and applies workflow.patch.
The repository workflow tests cover the new issue-58 input gate and compare the
installed workflow byte-for-byte to the reviewed candidate. The existing required
accounting CI check now also runs the exception unit tests and its 21-test
network-isolated disposable PostgreSQL harness. No migration or grant is applied
by CI or by merging. The earlier nine policy.py prototype tests are not included
in this release; the ten runtime/artifact tests are included.
