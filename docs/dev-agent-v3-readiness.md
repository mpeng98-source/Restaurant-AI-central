# Chubby Dev Agent v3.0 readiness review

Review date: November 3, 2026, America/Los_Angeles. Reviewed main:
`a6d052297249119d6e6315ab828104e9b66f2b55` (PR #49).
Remediation: [Draft PR #50](https://github.com/mpeng98-source/Restaurant-AI-central/pull/50).
This is a point-in-time review. Live state changed during the review; recheck
before authorization. **NO-GO for paid bootstrap today; NO-GO for coding canary.**
No paid request, workflow activation, database write/permission change, merge,
schedule or deployment was performed by this review.

## Findings and remediation

| Finding | Evidence and disposition |
| --- | --- |
| Unbounded coding spend / floating runtime | The pinned Codex action installs CLI/proxy without `codex-version`; `model` is unset. A $5 reservation cannot constrain actual multi-request token spend. PR #50 puts an unconditional hold in the first approval job, before collection or reservations. Removing it requires separately reviewed runtime/model pins and tested per-run request/input/output bounds, retry policy and spend controller. A job timeout is not a dollar cap. |
| Shared repository credentials | UI lists `OPENAI_API_KEY` and `CHUBBY_DEV_AGENT_PR_TOKEN` as repository secrets. The Codex and publisher Environments have no secrets, so the old workflow would fall back to shared values. PR #50 uses environment-specific `CHUBBY_CODEX_OPENAI_API_KEY`, `CHUBBY_PUBLISHER_TOKEN_V3` and `CHUBBY_BOOTSTRAP_OPENAI_API_KEY`; these new secrets are not yet provisioned. Secret names do not prove underlying key scope. Owner must migrate/revoke the old repository credentials after checking all consumers. |
| Permanent claim not protected | Public ruleset listing returned `[]`; claim ref returned 404. PR #50 requires an active, no-bypass tag ruleset preventing updates and deletion before claim creation. `ops/dev-agent-bootstrap-tag-ruleset.json` is the exact proposed ruleset, not an applied change. |
| NOINHERIT does not prevent SET ROLE | Existing audit only checks owner/neon-superuser memberships. PR #50 rejects any parent membership on service roles and any unsafe Dev Agent login, including legacy names. Two real-PostgreSQL regression tests cover this. |
| Rerun after an earlier pre-reservation failure | Old Context accepted arbitrary positive attempts when constructing a fresh plan. PR #50 denies every coding attempt other than 1 in context and workflow admission, even when no previous reservation exists. |
| Legacy privileged login observed, then removed externally | Initial live query found `dev_agent_permit_verifier_login` with CREATEDB, CREATEROLE, INHERIT, BYPASSRLS and neon_superuser membership. Later owner and auditor queries returned no such role, and zero active sessions used it. This review did not remove it. Current guard returns safe, but provenance of external cleanup and retired credentials still needs owner confirmation. |
| Main branch unprotected | Ruleset listing is empty; authenticated Branches settings show no protection rules. The detailed protection API is inaccessible to the connector (403). Owner must configure PR review, required checks, force-push/deletion protection and workflow change controls before launch. |

The retired v1/v2/v2.1 workflows contain only a failing retirement job, no Codex
action or secrets. The only coding action in current source is the protected
manual DAG. Other legacy audit/collector workflows contain no model invocation;
their summaries cannot replace authenticated cost evidence. No schedules were
found. Publication uses a fresh runner, validates existing allowlisted paths,
and uses create-only GitHub operations to publish Draft PRs. No automatic merge
or deployment exists. Model-produced test files remain untrusted executable code
when a later PR CI runs; use read-only/no-secret PR CI and human review.

## GitHub configuration actually inspected

All 12 pre-existing Environments were inspected in the authenticated settings UI.
Each requires reviewer `mpeng98-source`, disallows administrator bypass, and allows
only branch `main`, no tags. Each currently permits self-review. This supports
owner manual approval, not independent four-eyes approval. Runtime bootstrap
requires prevent-self-review; that stronger policy is configured separately.

| Environment | Visible secret names |
| --- | --- |
| dev-agent-run-approval-v27 | none |
| dev-agent-control-audit-v27 | DEV_AGENT_AUDIT_DATABASE_URL |
| cost-audit | OPENAI_ADMIN_KEY, DEV_AGENT_COST_SIGNING_KEY |
| cost-writer-v27 | DEV_AGENT_COST_SIGNING_KEY, DEV_AGENT_COST_WRITER_DATABASE_URL |
| dev-agent-reserver-v27 | DEV_AGENT_PERMIT_HMAC_KEY, DEV_AGENT_RESERVER_DATABASE_URL |
| dev-agent-verifier-v27 | DEV_AGENT_PERMIT_HMAC_KEY, DEV_AGENT_VERIFIER_DATABASE_URL |
| dev-agent-codex-v27 | none |
| dev-agent-publisher-v27 | none |
| dev-agent-failure-v27 | DEV_AGENT_FAILURE_DATABASE_URL |
| dev-agent-settlement-v27 | DEV_AGENT_SETTLEMENT_DATABASE_URL |
| dev-agent-control (legacy) | DEV_AGENT_CONTROL_DATABASE_URL |
| dev-agent-permit-verifier (legacy) | DEV_AGENT_PERMIT_VERIFIER_DATABASE_URL |

Secret values were not read, copied or logged. Equal signing-secret names do not
prove the values match. Underlying database URL identities in GitHub secrets
remain unverified by this review's connector-mediated logins.

Prepared environment: `dev-agent-bootstrap-v1`, ID `26216386226`.
UI confirmed reviewer `mpeng98-source`, prevent-self-review **on**, administrator
bypass **off**, exactly branch `main`, zero allowed tags, no environment secrets
or variables. Creating it did not activate a workflow. Repository variables show
`CHUBBY_DEV_AGENT_GATED_ENABLED=false` and the expected Project ID; bootstrap
activation is unset. No switch was changed. The current bootstrap cannot proceed
with an owner-dispatched run and the same owner as its only reviewer: arrange a
different authorized dispatcher or independent reviewer; do not disable self-review.

## Actual Neon evidence (read-only)

Target: project `super-pond-95165425`, production branch
`br-super-glade-arow66co`, database `dev_agent_control_db`.

- v27 NOLOGIN owner and all six LOGIN service roles have no superuser,
  CREATEDB, CREATEROLE, INHERIT, BYPASSRLS or parent-role memberships.
- All five accounting tables are owned by `dev_agent_accounting_owner_v27`;
  their visible ACLs grant only that owner table access.
- All eight accounting function bodies match the reviewed migration bodies by
  database body fingerprint. SECURITY DEFINER owners, fixed
  `search_path=pg_catalog, pg_temp`, and exact EXECUTE ACLs match the source.
  PUBLIC and the retired raw functions have no service-role EXECUTE grant.
- Connector-mediated real logins verified both current_user and session_user as
  auditor, cost writer, reserver and verifier in the correct database. Writer,
  reserver and verifier have no direct reservation-table privileges/memberships.
  These are real role logins, not SET ROLE fixtures; they do not prove the GitHub
  secrets carry these same credentials.
- Auditor `rollout_status` returned project_enabled=true, legacy_pending=0,
  legacy_today=0, unbound_pending=0. Owner count queries returned **0 cost rows,
  0 reservations, 0 permits, 0 settlements, 0 legacy reservations**.
- Production branch metadata reports protected=false. Consider branch protection
  as an owner configuration task; no branch setting was changed.

No synthetic rows or permission changes were made in live Neon. Do not use the
empty tables as evidence of zero OpenAI spending.

## OpenAI and bootstrap evidence

Project UI confirms `Chubby-Dev-Agent` = `proj_Nkd1G85QX72VHwdQ8mEg8CRa`, matching
source and GitHub variables. The All project keys list returned 0 results. Its last-seven-day dashboard shows no spending rows,
0 requests, 0 tokens. Default project separately shows 35 requests and $0.48;
those records cannot authorize the Chubby project. Encrypted GitHub keys cannot
be matched to the project through metadata alone. Owner must provision the new
project-scoped environment key. Account-specific model entitlement remains a
live acceptance item; official availability is not proof of this key's access.

The [current model documentation](https://developers.openai.com/api/docs/models/gpt-6-luna)
lists gpt-6-luna with reasoning=none and standard rates of $0.10/M input,
$0.50/M output; cache writes $0.125/M. The fixed `Reply OK.` probe with no tools
and max_output_tokens=16 is far below the **$0.01 estimated allowance**: even
1,024 input tokens plus 16 output tokens estimate $0.0001104, or $0.000136 if
all input were cache writes. Other project traffic is outside this estimate.
No provider-enforced dollar cap is claimed. Model name has no documented dated
snapshot. Pricing approval expires **2026-11-07 00:00 UTC** (November 6, 4 PM PST).

Bootstrap has one fixed project, one permanent repository-wide tag, atomic
create-ref admission, no redirect/retry, and rejects all reruns. Eight-way
concurrency is tested against a simulated GitHub atomic create-ref contract,
not by racing paid calls. HTTP errors, timeout, cancellation, response rejection
or process death after claim creation burn the opportunity. No reset/delete path
exists. Returned text is discarded. Bootstrap cannot emit signed costs or a
coding permit, change a switch, publish a PR or invoke Codex.

Latest existing protected cost diagnostic
[41779697401](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41779697401)
failed closed with COST_PROJECT_COSTS_UNKNOWN. No new OpenAI API request was made
by this review. Real billing source authentication and ingestion remain Phase 3,
after separate approval and bootstrap, not completed integration evidence.

## Tests and evidence limits

Local: 71 offline tests pass, including bootstrap atomic admission, role-related
context checks, unavailable/invalid cost responses, signatures, expiry, trusted
bindings, proposal publication, and the unconditional pre-collection hold.
Hosted acceptance adds real disposable PostgreSQL tests for concurrency, six/day,
$10 exposure, $5 reserves, signature/replay, cost freshness and settlement.
New tests exercise invalid/expired signature, exceeded budget/stale cost and
unavailable DB through a model callback that must remain uncalled.

Main after PR #49: [accounting acceptance 41782019872](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41782019872)
and [full regression 41782019869](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41782019869)
passed. PR #50 CI results are recorded in its description at the exact head.

| Denial scenario | Evidence level |
| --- | --- |
| Invalid/expired signature, wrong run/SHA, replayed nonce | Offline cryptographic and real disposable PostgreSQL acceptance; no model callback |
| Duplicate run, eight concurrent consumers, daily quota/budget | Real disposable PostgreSQL acceptance; no live production reservation |
| Stale, missing, wrong-project/unsigned costs | Collector offline rejection + PostgreSQL freshness checks; existing live missing-cost denial |
| Neon unavailable | Injected OperationalError, model callback uncalled; no induced live outage |
| Environment approval denied | Source DAG requires successful approval; live rejection not dispatched/tested |
| Timeout/cancellation | Bootstrap burns claimed opportunity; coding reservations stay unresolved, never auto-release; no induced paid timeout |
| Rerun | Bootstrap rejects attempt !=1; PR #50 also rejects fresh coding plans for attempt !=1 |
| Issue -> Draft PR | Simulated bounded callback/publication tests only; no complete paid chain yet |

Reported project cost plus unresolved reservations is deliberately conservative:
it may count an already-reported pending run within both reported totals and its
full reserve until independent finality review. It is not exact per-run spend.
Settled/cancelled_verified reservations are excluded from pending sums; previous-day
unresolved reserves remain. Settlement requires independently reviewed evidence
and a minimum buffer, never elapsed time or a failed job alone. Existing tests
cover release-once/concurrency and removing settled reserves without charging
them twice. Do not loosen this policy to improve availability.

## Owner steps, in order (no paid authorization requested yet)

1. Review PR #50 and its exact-head CI, then separately authorize merge. Its
   coding hold must remain until bounded-inference acceptance is implemented.
2. Review/apply the tag ruleset JSON through Settings -> Rules -> Rulesets ->
   New tag ruleset. Active; exact tag `chubby-dev-agent-bootstrap-v1`; no bypass
   actors; restrict updates and deletions; leave creation allowed. Verify through
   GET /repos/mpeng98-source/Restaurant-AI-central/rulesets and /rulesets/{id}.
   Do not create the actual claim tag during setup.
3. Provision a dedicated Chubby-project key with only required inference access,
   constrained to gpt-6-luna where project model controls support it. Add it as
   **CHUBBY_BOOTSTRAP_OPENAI_API_KEY** only in dev-agent-bootstrap-v1. Owner must
   enter credentials directly; do not send them in chat. Verify repository has
   no same-name fallback. Later use a separate CHUBBY_CODEX_OPENAI_API_KEY in
   dev-agent-codex-v27 and CHUBBY_PUBLISHER_TOKEN_V3 in dev-agent-publisher-v27.
   Remove/revoke old shared repository keys after reviewing their consumers;
   do not copy/reveal existing values through this chat.
4. Arrange distinct dispatcher/reviewer identities for bootstrap; keep prevent
   self-review and administrator-bypass prohibition. Verify main governance and
   confirm external legacy-role cleanup/credential revocation.
5. Recheck exact project, current model entitlement/pricing, expiry, tag absence,
   environment settings and all switches. Keep coding=false and bootstrap unset
   until the separate paid approval. Do not infer authorization from this report.
6. When all above pass, owner may explicitly approve **one fixed bootstrap probe,
   USD 0.01 estimated allowance, no automatic retry**, on a named merged SHA.
   Only then set bootstrap=true and dispatch on main with approved_sha equal to
   that SHA and confirmation `ONE PROBE; USD 0.01 ESTIMATE; NO RETRY`. A different
   required reviewer approves the environment wait. This review did not dispatch.
7. After that one attempt, retain the permanent tag, return bootstrap=false and
   keep coding=false. An uncertain outcome is not permission to retry. Await actual
   Costs rows for the exact UTC day; do not use yesterday's/Default project costs.
8. After separate Phase 3 approval, collect/sign in cost-audit and verify/ingest
   in cost-writer-v27 with immutable source/run/attempt and fresh project/day data.
   A standalone v27 protected reconciliation workflow is still needed: the old
   v26 manual importer targets absent v26 environments and is not accepted as a
   ready production path. Do not enable the coding workflow merely to ingest costs.
9. Keep existing low-risk [Issue #46](https://github.com/mpeng98-source/Restaurant-AI-central/issues/46)
   as the single canary (one existing inventory-count documentation clarification).
   This review removed agent-approved and retained agent-safe. Only restore its
   approval after the full readiness checklist and separately approved paid
   canary, with a task digest and reviewed SHA. Never combine bootstrap approval
   with coding authorization.

Go decision: **NO-GO** for either paid step until its own blockers are resolved.
After tag protection, dedicated key verification, distinct reviewer, reviewed
merge and revalidation, only the one-time bootstrap can be considered for Go.
Codex remains No-Go until bounded spend/pinned runtime, authentic cost ingestion,
GitHub secret isolation and the complete approved Issue -> Draft PR acceptance
are independently demonstrated. Preserve six/day, $10/day, $5/run reservation,
manual-only operation, no auto-merge, and no production deployment.
