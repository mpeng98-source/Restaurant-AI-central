# Restaurant platform completion plan

**Evidence snapshot:** `main` at `d5fb06c24e94305c09f78bd0f719554a6853425f` (2026-11-05).

**Scope:** iPad-first, multi-tenant restaurant operations. This is a product completion inventory, not authorization to merge or deploy.

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

### P0 — Tenant-safe, auditable operational core

- Every API resolves organization and location access from authenticated assignments; cross-organization and cross-location access fails at both API and PostgreSQL RLS layers.
- Count, approval, rejection, opening, and correction operations are authorized, audited, concurrency-safe, and idempotent. No rejected or unapproved report changes stock; posted ledger/audit records are immutable and corrections append compensating movements.
- Quantities remain decimal-safe, explicit-unit validated, and baseline-aware. A missing baseline is never silently treated as zero.
- Count entry exposes validation errors on the affected control to assistive technology; loading, empty, offline, conflict, and success states distinguish unsaved work from confirmed server state.
- Backend/PostgreSQL security and frontend tests, migrations, Compose runtime, secret scan, and the repository's existing required checks pass with zero required skips.

### P1 — Complete the controlled restaurant workflow

- After owner review, reconcile and merge the existing #7 then #9 work in dependency order; preserve all existing migrations and do not bypass review.
- An authorized operator can establish opening stock from approved source data, then complete a count, independent review, approval/rejection, and reversal rehearsal with ledger and audit reconciliation.
- Protected evidence is private, scope-checked, validated, retained/deleted under an approved policy, and never used to infer quantity.
- Complete signed physical-iPad Safari UAT in portrait and landscape with employee and GM/Owner accounts, including retry/double-tap, refresh, network loss, auth expiry, camera permissions where applicable, and location isolation.

### P2 — Operational expansion after verified integrations

- Add receiving, waste, transfer, production, and other stock-changing workflows only with explicit actors, permissions, idempotency, audit, and append-only ledger semantics.
- Integrate POS/theoretical depletion or vendor workflows only after a verified external contract, reconciliation design, tenant-safe integration tests, and explicit human approval boundaries exist.
- Validate multi-organization operations, support procedures, monitoring, recovery, and a separately approved staging/pilot release before considering production deployment.
