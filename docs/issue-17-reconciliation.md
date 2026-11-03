# Issue #17 — Sprint 2B integration with main

This integration preserves Sprint 2B counting and main's Dev Agent changes without a rebase or force push. PR #3 was squash-merged into main; its original inventory commits remain in the feature branch, so Git's actual common ancestor is `c53d18f7c2a2dc5674ad2f370515ebfd8159488f`.

## Inputs and scope
- Main: `fde2d3de25a0d51cf29a34b6430c6e0b07c345f2`.
- Original PR #5 head: `c982b9616a24b6c5681cc253668cc83fce8ab9bf`.
- Merge commit parents retain that PR head first and main second. No PR merge or production deployment is authorized.
- Work was prepared in an isolated local Git object repository; the shared working directory contains later Sprint 2D changes and is not a source for this integration.

## Exact conflicts and reviewed resolutions
Native `git merge-tree --write-tree` reproduced exactly two add/add conflicts:
1. `backend/app/inventory_models.py`: retain the original Sprint 2B file, including `assigned_to`, zone scope, version, cutoff, quantity/percentage thresholds, `under_review`, `counted_by` and JSONB snapshots. Its changes from main are precisely the intended count-model extension. The StockMovement class AST is identical to main; quantities, composite scope constraints, reversal and idempotency checks are unchanged.
2. `backend/tests/test_inventory_units.py`: retain main's file. AST comparison confirms every pre-existing Sprint 2B test body remains identical, and main's `test_item_specific_case_conversion_returns_decimal_pieces` is retained.

`.github/workflows/sprint-1b.yml` merged automatically. Against main, its only functional addition is Sprint 2B's frontend login/workspace/inventory route smoke step. Main's Dev Agent v2 security regression job, change-gate tests, script compilation, required PostgreSQL/Redis checks, frozen lockfile frontend checks, Compose and Gitleaks jobs remain intact. Main's Dev Agent workflows/prompts/scripts/docs are copied unchanged.

## Preserved invariants
- Migrations `0001_foundation` and `0002_inventory` match main and the original branch byte-for-byte.
- `0003_inventory_counting` is identical to the original PR #5 revision. No migration is rewritten or renumbered.
- Authorization, RLS policy SQL, CSRF enforcement, assignment checks, frozen variance snapshots, ledger cutoff/posting clock, Decimal conversion, version checks and existing security tests retain the original branch content.
- Count submission/review does not post inventory adjustments. Stock updates/deletes/truncation remain blocked; later approval/reversal functionality remains in PR #7.
- The proposed code diff against main is exactly the 12 intended Sprint 2B paths, plus this audit document. Main's added Decimal test is unchanged relative to main.

## Verification
Local Git conflict reproduction, model/test AST preservation, complete file-mode/blob comparisons and workflow parsing are recorded during preparation. Full hosted acceptance is required at the published merge head: real PostgreSQL 16/Redis 7, migration through 0003, backend/auth/RLS/count/concurrency tests with zero skips, Dev Agent gate security tests, frontend typecheck/lint/build, Compose health/runtime and Gitleaks tree/history. Exact executed results and final SHA are maintained in PR #5's description after CI finishes; this document does not predeclare a passing run.

## Descendants and human review
PR #7 remains at `537e2d820ee5f5eaeb56d61c7e174586e5c1a3b8`, targeting `codex/sprint-2b-counting`. PR #9 remains at `acdf82372d8fb047b791ebd724fb2f7aa7741903`, targeting `codex/sprint-2c-approvals`. Their branches are not changed in this step. Both retain their original migrations and intended approval/pilot implementations.

Propose a separate reviewable follow-up: merge the updated PR #5 branch into #7, inspect its diff and run full CI; then integrate that refreshed #7 into #9 with the same checks. Do not force-push or infer descendant verification from PR #5's CI.

The model conflict concerns fields used by location/assignment authorization, so a human must review its resolution and migration/model agreement before any owner-authorized PR merge. This integration does not approve a pilot, certify physical iPad Safari, or authorize deployment.
