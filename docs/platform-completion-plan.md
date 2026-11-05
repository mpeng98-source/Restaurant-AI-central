# Restaurant platform completion plan

**Evidence snapshot:** `main` at `d5fb06c24e94305c09f78bd0f719554a6853425f` (2026-11-05).

**Current scope (owner decision, 2026-11-05):** internal, noncommercial demo using synthetic data and test accounts only. AI review, remediation of confirmed findings and relevant automated tests are the demo review standard; independent human security sign-off is **not a demo requirement**. This is not authorization to merge or deploy.

## Current internal-demo acceptance

This section supersedes earlier statements below that made live-restaurant resources or independent human review prerequisites for all progress. Earlier verification records remain historical evidence; their live-pilot requirements apply only to a future live pilot.

- Use synthetic catalogs, quantities, photos and test accounts only. No real restaurant records, personal employee data, production credentials or operational stock changes.
- Preserve authentication/CSRF, server-derived tenant/location authorization, forced PostgreSQL RLS with a restricted runtime role and transaction-local context, immutable audit/ledger history, independent proposer/approver controls and human confirmation of inventory actions. Synthetic data does not justify bypassing these controls.
- Use AI code review and relevant tests. Confirmed request-validation defects V1/V2 in [the AI review](platform-ai-review.md) were fixed across the branches; unknown fields return 422 without mutations. AI review is not described as independent human approval or a security certification.
- Require passing current-version automated checks for the demonstrated capabilities, and an explicit demo walkthrough showing test-user count, review/approval/rejection, synthetic opening/photo and reconciliation behavior. The separate PR #56 UX and PR #9 pilot feature branches have not yet been combined; a combined demo version and its checks must be prepared before claiming the complete demo works.
- Clearly mark all demo screens/materials/data as synthetic or simulated. WebKit is browser emulation; development sanitizer-only photos are not antivirus-certified. No physical iPad/camera, production SMTP, real scanner/signature monitoring, live catalog accuracy, multi-host storage or paired staging evidence recovery is claimed.
- Physical-device acceptance, real antivirus, restaurant data rehearsal, independent human security sign-off and controlled live staging/recovery are **not required for this synthetic demo**. They remain separate live-pilot gates if that scope is later approved.
- Merge and deployment still require separate owner authorization; neither is authorized now. A test runtime or local walkthrough is not a staging deployment.

### Demo next steps and remaining limits

1. Prepare a combined working branch that retains the existing PR #56 count UX/recovery and PR #7/#9 inventory features without rewriting migration history or duplicating implementation; rerun relevant tests on its exact SHA. This is branch integration, not merging PRs into main.
2. Prepare and verify a synthetic/test-account demo walkthrough with visible simulation labels, preserving all security and inventory approval checks.
3. Record actual demo results and unresolved failures. Do not use historical branch checks as proof of the combined version.
4. Ask for separate merge/deployment authorization only when that action is desired. No reviewer hire, restaurant data, scanner purchase or staging access is needed merely to progress this demo.

### Private internal-test deployment preparation

The owner requested a separately approved synthetic test deployment. Configuration and cost/HTTPS/private-network/managed-secret/account-setup/rollback procedures are in [the deployment package](internal-test-deployment.md), on `codex/internal-demo-deployment`. That branch combines the completion-plan and pilot features without merging PRs into main. The native merge preserved both sets of behavior, including photo-aware unsaved-entry checks. Hosting purchase/access/deployment remains unapproved until the package is reviewed. No test URL, cloud deployment, live restaurant data, SMTP or scanner certification is claimed; uploads remain fail-closed without a scanner.

## Evidence rules

- **Verified on main** means the behavior exists in the checked-out source and has corresponding tests or CI evidence.
- **Unmerged** means the work is present only on an open pull request; its branch-level tests do not make it part of `main`.
- **Unverified** means the repository or available CI evidence does not establish that the capability works in its intended real environment.
- Future acceptance criteria below are targets, not claims about current behavior. No staging, physical-device, or production result is inferred from local code or browser emulation.

## Implemented on `main`

| Capability | Evidence and limits |
|---|---|
| Tenant and location foundation | Organizations, locations, users, roles, permissions, assignments, sessions, and audit records are modeled in the foundation migration and application (`backend/migrations/versions/0001_foundation.py`, `backend/app/models.py`). The server authorizes location access from the authenticated principal; tenant/location context is transaction-local and PostgreSQL RLS is forced (`backend/app/authorization.py`, `docs/security-model.md`). Real PostgreSQL security tests exercise missing context and cross-scope isolation (`backend/tests/test_postgres_security.py`). |
| Identity and session security | Invite-only authentication, Argon2id password hashes, opaque server-side sessions, CSRF checks, reset-token expiry/replay handling, and location-aware permissions are implemented in `backend/app/auth.py`, `backend/app/security.py`, and `backend/app/authorization.py`. |
| Auditing and operational foundation | Audit records are protected from ordinary update/delete, and Redis/worker services are foundations rather than autonomous business-action executors (`docs/architecture.md`, `docs/operations.md`). AI recommendations remain proposals; no automatic stock or purchasing action is authorized (`AGENTS.md`). |
| Inventory catalog and stock ledger | Migration `0002_inventory` adds location-scoped inventory, units/conversions, zones, and append-only stock movements. `backend/app/inventory_units.py` uses `Decimal` and explicit item-specific pack factors. PostgreSQL tests cover RLS, ledger immutability, actor scope, and idempotency (`backend/tests/test_inventory_postgres.py`, `backend/tests/test_inventory_units.py`). |
| Employee count and variance workflow | Migration `0003_inventory_counting` and `backend/app/inventory_counts.py` implement assigned draft sessions, version checks, unique lines, decimal quantity/unit validation, submission cutoff snapshots, baseline-required handling, and review-only variance. Submission does not post stock movements. API/PostgreSQL tests cover cutoff, baseline, concurrency, retries, assignment, validation, and RLS (`backend/tests/test_inventory_counting.py`). |
| Inventory counting UI | `frontend/app/inventory/page.tsx` provides authorized location selection, catalog search, units, notes, draft save/remove, submit/reload, loading, error, empty, offline, and success states. Quantity validation prevents negative values and precision beyond six decimal places, but before this task its message was only in the page-wide alert rather than associated with the invalid field. The UI explicitly says that submissions do not change balances. `frontend/tests/smoke.mjs` checks route rendering and absence of an unsupported photo-upload control. |
| Hosted baseline checks | On the evidence snapshot, the latest `main` push passed five existing PR check runs: Dev Agent v2 security regression, Backend/PostgreSQL security and frontend, Docker Compose runtime, full repository/history secret scan (Sprint 1B run `41913663238`), and authenticated costs/settlement/permit concurrency (run `41913663152`). Repository branch-protection settings could not be read with this session token (GitHub API returned 403), so whether each check is marked required by branch protection is not independently verified here. |

## Open, unmerged inventory work

| Pull request | State and dependency | Branch evidence (not main) |
|---|---|---|
| [#7 — Sprint 2C approvals](https://github.com/mpeng98-source/Restaurant-AI-central/pull/7) | Draft/open, targets `main`; implements independent GM/Owner approval and rejection, four-eyes review, exactly-once adjustment posting, stale-ledger conflict handling, compensating reversals, and approval UI. Adds migration `0004`. Do not duplicate these features or treat them as merged. | `gh pr checks` reported all four Sprint 1B jobs passing on head `2f0ae6952150738460f7d3a1b5859faf8c8ef213` (run `41740256624`); the PR reports 73 backend/PostgreSQL tests and four WebKit scenarios passing. |
| [#9 — Sprint 2D pilot readiness](https://github.com/mpeng98-source/Restaurant-AI-central/pull/9) | Draft/open, stacked on #7; adds explicit opening balances, protected evidence storage/access, catalog import and operational reconciliation/CLI, pilot guidance, and migration `0005`. It depends on #7 and must remain distinct from main until the stack is approved. | `gh pr checks` reported all four Sprint 1B jobs passing on head `9d8dcf0f770b688f471eda325e39a1470aefee57` (run `41740881413`); the PR reports 124 backend/PostgreSQL tests, six WebKit scenarios, and seven operational CLI commands passing. |

The PR descriptions and diffs were inspected along with open issues #2, #4, #6, #8, and #18. Issue #18 documents the integration order and explicitly forbids merging either draft without separate owner approval. These PRs change the inventory page, but neither adds the field-associated count validation delivered in this branch.

## Verified gaps and unverified assumptions

### Verified gaps on `main`

1. **Count-entry error association:** invalid quantities are rejected, but the error is only rendered in a generic page alert. The quantity input has a label but no invalid state or field-specific error association. The bounded frontend change in this PR adds that association without changing the backend contract.
2. **Approval and correction workflow:** not present on `main`; implementation is unmerged in #7.
3. **Opening balances and protected evidence:** not present on `main`; implementation is unmerged in #9. The 2B API only accepts opaque photo metadata and exposes no upload control.
4. **No verified POS/theoretical depletion integration:** current product documentation explicitly says Toast integration is not available; ledger balances therefore cannot be claimed as live POS-derived theoretical stock.

### Unverified

- Real-device iPad Safari portrait/landscape, camera permissions, touch ergonomics, and network-loss recovery have not been established by CI. WebKit emulation on a CI runner is not physical iPad acceptance.
- A production deployment, production SMTP, a live multi-host protected-object-storage configuration, and a paired staging backup/private-evidence restore are not established by this repository snapshot.
- Catalog quality, initial stock accuracy, and operator readiness depend on owner-approved restaurant data and an observed reconciliation rehearsal.

### Assumptions for planning, not verified results

- Additional organizations and locations should use the existing tenant/location model and assignments, with authorization derived server-side; adding locations must not require per-location schema changes.
- Operators need usable count and review flows on iPad-sized touch screens. The required device/browser matrix and restaurant-specific workflows still need owner confirmation during acceptance.
- Pending PR descriptions accurately summarize their intended behavior, but only their listed branch checks establish the reported automated verification, and neither branch is merged.

## Dependencies and guardrails

- Keep tenant/location authorization in both application checks and PostgreSQL RLS; never rely on a client-supplied location ID alone. Keep app DB credentials restricted and transaction-local tenant context fail-closed.
- Preserve migration history and append-only audit/stock records. Schema work requires a new migration and real PostgreSQL upgrade/security coverage.
- Keep every financial, HR, and inventory action under explicit human authorization. AI output is advisory only; do not add automatic ordering, stock adjustment, or Toast depletion.
- Resolve the #7 approval/reversal stack before treating #9 pilot setup as complete. Neither draft PR is approved for merge or deployment by this plan.
- Keep all existing required CI checks; use normal pull-request events for hosted verification. Do not edit workflows, admission/bootstrap controls, GitHub settings, credentials, or agent flags as part of this plan. No custom coding-agent development or activation is in scope.
- Obtain owner-approved catalog, units/conversions, opening quantities, retention policy, and named reviewer/counter assignments before any live pilot.

## Prioritized acceptance criteria

### 2026-11-05 development progress and blockers

The Sprint 2D refresh is published at `5ec312eff03b8cb95184a69434d9bfc648a3fd47`, with latest Sprint 2C base `efe74a6b29609b2d26d9c3b5df4c73bee0dc361b` as second parent. The integration-history conflict is resolved without replacing application code, migration history, dependency locks or existing security gates. Fresh hosted runs 41978774387 and 41978774410 passed all five checks; downloaded artifacts confirm 124 backend tests and six WebKit scenarios with zero failures/skips, and hosted logs confirm seven authenticated CLI commands. These runs also passed frontend checks/build, Compose runtime/privacy, legacy migration integrity, synthetic database restore and secret scans. PR #7 must still be independently approved and merged into main before PR #9 is retargeted and reviewed.

Independent P0 follow-through on this completion-plan branch adds a visible unsaved-count status, precise decimal-aware dirty detection, and discard confirmation before opening/reloading another session, switching restaurants, creating a draft, changing assignment or following workspace links. Tab close/refresh registers the browser's standard unsaved-work warning; browser support, including physical iPad behavior, still requires UAT. Canceling an in-page discard keeps entries in memory; saving one item does not erase other unsaved items. This is not offline persistence or automatic synchronization, and browser history/device termination can still lose in-memory entries.

The requested development container reads Node.js and pnpm pins from the existing manifests and installs them during image creation, avoiding repeated `npm exec` downloads during routine checks. It does not provision application secrets or Docker host access. Its frozen dependency install and normal `pnpm` check commands are documented in the README.

Local verification: the development image built successfully and a fresh non-root container reported Node.js 24.22.2, pnpm 11.25.0 and Python 3.12.11. A second fresh container installed the frozen frontend lock and ran TypeScript 5.8.3 without `npm exec`. The configuration is committed on this working branch and persists across sessions that open it as a dev container; the temporary session toolchain does not configure unrelated future agent hosts. Version changes require an image rebuild.

Count UX validation: seven quantity/dirty-state regression tests passed with zero failures/skips, covering explicit zero, exact large Decimals, changed quantity/unit/note, cleared saved counts and preservation of other unsaved entries. Pinned-toolchain typecheck, ESLint, production build and live frontend HTTP route smoke passed. The corresponding head `f0679d7353804125c4ca7bf24f6fababe5847640` passed all five hosted checks in runs 41980464547 and 41980464543, including 47 backend tests and the seven frontend regressions with zero required skips. Browser discard-dialog automation and physical-device lifecycle behavior are not claimed verified.

Physical iPad/camera UAT, independent human security approval, real antivirus/signature monitoring, owner-approved catalog and signed-sheet rehearsal, paired staging database/private-evidence recovery, external SMTP, and merge/deployment approval remain blocked on their actual evidence or owner input. No new external integration, operational data import, autonomous stock mutation or custom-agent activation is authorized.

### Next P0 follow-through: count request recovery

The existing count client said changes were not saved on generic HTTP failures, including server errors that can arrive after a committed write. Count requests now distinguish definite rejections from uncertain mutation outcomes: network loss, HTTP 5xx, interrupted or malformed success responses require reloading server state before retry, without automatic replay or a claim that no save occurred. HTTP 401 explicitly asks for renewed sign-in and reload; HTTP 409 requires the latest version. Both preserve entries in memory through the existing error/dirty-state controls. Read failures report unavailable server state rather than mutation outcomes. API validation/permission details, credentials, CSRF headers, exact Decimal payloads and versions are retained.

Regression coverage is wired into the existing hosted smoke command without workflow changes. The verified devcontainer is used for local frontend checks. This adds no offline persistence, cross-device recovery guarantee, session extension or authorization bypass. Physical iPad/network-loss acceptance and all other manual pilot gates remain open.

Local verification of request recovery ran in the verified image as the non-root `vscode` user with Node.js 24.22.2 and pnpm 11.25.0. All 22 frontend regression tests (15 new request cases plus seven existing quantity/draft cases), TypeScript, ESLint, production build and live HTTP smoke passed with zero test failures/skips. The first attempt to share host `node_modules` failed pnpm's unsafe-directory check; rather than disabling that safeguard, validation used a disposable source copy and a frozen-lock install inside the container. No toolchain redownload through `npm exec`, host dependency modification, workflow edit or new dependency was needed. The temporary server/container exited after validation. Fresh published-head hosted outcomes are recorded on PR #56 after completion.

Published request-recovery head `d39a32945e0eeba6cb0d65317a15294b8fbd61ba` passed all five hosted checks in runs 41982666614 and 41982666580. CI confirmed 47 backend tests plus all 22 frontend regressions with zero failures and zero skipped tests, TypeScript, ESLint, production build, PostgreSQL/Redis runtime, Compose health/startup/shutdown, security regressions and full-history secret scan. This verifies automation on that branch only; it is not physical-device acceptance or a live pilot.

### Future live-restaurant work and blockers (not internal-demo prerequisites)

- **Stack integration/release:** PR #7 has a clean diff and green hosted checks but is still draft and unmerged. PR #9 is stacked on it. The next merge/rebase order is PR #7 into `main`, then PR #9; both require separate explicit owner approval. Do not treat clean mergeability as approval.
- **Independent review:** requires a named human reviewer and recorded review evidence; the author/self-review and automated checks do not satisfy it.
- **Operational acceptance:** physical iPad Safari/camera/network-loss/auth-expiry UAT, real antivirus/signature monitoring, an owner-approved catalog and signed manual sheet, and paired staging PostgreSQL/private-evidence recovery require actual devices, approved business inputs, and a controlled environment. They remain unverified.
- **Production readiness:** SMTP delivery, provider/multi-host storage guarantees and deployment remain out of scope/unverified; no credentials, access, spending authorization, merge permission or deployment approval are inferred.

Repository implementation cannot verify these external live-pilot gates. They do not block the synthetic internal demo described above; combined-branch integration, synthetic labeling and walkthrough validation can continue independently. They also do not authorize merging or deployment.

### P0 — Tenant-safe, auditable operational core

- Every API resolves organization and location access from authenticated assignments; cross-organization and cross-location access fails at both API and PostgreSQL RLS layers.
- Count, approval, rejection, opening, and correction operations are authorized, audited, concurrency-safe, and idempotent. No rejected or unapproved report changes stock; posted ledger/audit records are immutable and corrections append compensating movements.
- Quantities remain decimal-safe, explicit-unit validated, and baseline-aware. A missing baseline is never silently treated as zero.
- Count entry exposes validation errors on the affected control to assistive technology; loading, empty, offline, conflict, and success states distinguish unsaved work from confirmed server state.
- Backend/PostgreSQL security and frontend tests, migrations, Compose runtime, secret scan, and the repository's existing required checks pass with zero required skips.

### P1 — Future live-restaurant workflow (separate scope)

- After owner review, reconcile and merge the existing #7 then #9 work in dependency order; preserve all existing migrations and do not bypass review.
- An authorized operator can establish opening stock from approved source data, then complete a count, independent review, approval/rejection, and reversal rehearsal with ledger and audit reconciliation.
- Protected evidence is private, scope-checked, validated, retained/deleted under an approved policy, and never used to infer quantity.
- Complete signed physical-iPad Safari UAT in portrait and landscape with employee and GM/Owner accounts, including retry/double-tap, refresh, network loss, auth expiry, camera permissions where applicable, and location isolation.

### P2 — Future operational expansion after verified integrations

- Add receiving, waste, transfer, production, and other stock-changing workflows only with explicit actors, permissions, idempotency, audit, and append-only ledger semantics.
- Integrate POS/theoretical depletion or vendor workflows only after a verified external contract, reconciliation design, tenant-safe integration tests, and explicit human approval boundaries exist.
- Validate multi-organization operations, support procedures, monitoring, recovery, and a separately approved staging/pilot release before considering production deployment.
