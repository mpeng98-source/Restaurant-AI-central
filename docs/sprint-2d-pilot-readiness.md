# Sprint 2D — implementation and verification record

Issue [#8](https://github.com/mpeng98-source/Restaurant-AI-central/issues/8), integrated under [Issue #18](https://github.com/mpeng98-source/Restaurant-AI-central/issues/18). Originally based on PR #7 commit `00b8f33bfdf354aab6838495ae5d0f162aa7d9ec`; the integration commit now includes verified 2C head `2f0ae6952150738460f7d3a1b5859faf8c8ef213` as its second parent, incorporating main `536635e92d6abd59d9ea6eb74830ac7e04d586a9`. Branch `codex/sprint-2d-pilot-readiness` remains stacked on `codex/sprint-2c-approvals`. PR #3/#5 are merged; PR #7/#9 remain draft and unmerged. No force-push, gate bypass, PR merge or production deployment is authorized or performed. The earlier 2C report describes its own capabilities; this increment adds its missing opening and protected evidence workflows.

## Database and API contracts

Migration `0005_inventory_pilot` follows 0004. Files 0001–0004 are byte-for-byte unchanged; a regression test pins their SHA-256 hashes. 0005 is forward-only, as financial history and evidence tombstones must survive a rollback of application code. It adds:

- Immutable opening requests, frozen item/name/SKU/unit/factor/quantity, and immutable independent opening decisions. Both are tenant/location scoped, forced RLS, security-invoker triggers/functions. Creation requires `inventory:catalog:manage`; decision requires `inventory:approve`. Proposer and reviewer must differ, including Owner proposals; a revoked proposer cannot create new requests, while a current independent reviewer may decide an existing immutable proposal. All sizes require two people, covering high-impact openings without inventing a financial threshold.
- One immutable nonzero `opening` movement after approval; explicit zero is an approved baseline record with **no zero-valued movement**. Missing baseline stays unknown. Approval is rejected if any ledger activity or approved opening already exists, or the reviewed catalog changes. Location advisory locks serialize opening requests, decisions, regular movement posting and count submission. Duplicate matching requests/decisions replay the same identity; changed inputs conflict. Competing decisions cannot double-post. Raw opening inserts are rejected even when the caller supplies plausible metadata.
- Explicit zero baseline recognition in the replacement count snapshot function. Existing cutoff, Decimal arithmetic, frozen snapshots, independent count decisions, receipt-conflict detection, compensating reversals and immutable audits remain enforced. Incorrect openings are corrected by a fresh physical count and independent adjustment review; they are never edited or deleted.
- Private evidence metadata, immutable identity/hash/size/scanner provenance, scoped parent session, retention deadlines, legal hold and permanent deletion tombstones. A count line may reference only live protected evidence belonging to that same session. Audit records cover uploads, lifecycle changes, grants, views and byte erasure.
- Finite PostgreSQL numeric checks reject NaN and infinities in quantities, factors, costs, thresholds and balances; positive/nonzero checks alone do not reject PostgreSQL NaN.
- Immutable catalog import, bulk-opening and manual-reconciliation operation records with idempotency fingerprints and audits. Restrictive policies additionally require catalog permission for catalog writes and approval/catalog permission for ledger inserts. Employee context cannot write catalog data or directly post movements.

Opening endpoints: `GET/POST /api/v1/inventory/locations/{location}/openings`; `POST .../openings/{request}/decision`; `POST .../opening-import/preview` and `POST .../opening-import`. Inputs require explicit confirmation, Decimal strings, reason and idempotency key. Bulk preview is digest-bound, bounded to 200 unique items, revalidated under lock, and imports proposals atomically. Each proposal still needs an independent decision.

Operational endpoints: `POST .../catalog-import/preview`, `POST .../catalog-import`, `POST .../reconciliation`. Catalog imports are create-only, 200 rows maximum, all-or-nothing, with a preview digest and human approval reference. They create categories, zones, ingredient items, enabled location records, vendors, mappings and explicit pack conversions. Global physical factors cannot be overridden. Existing SKUs/conversions are never silently changed. Reconciliation normalizes signed manual sheet lines, compares the committed ledger under the posting lock, reports unknown baselines and differences, and records **zero movements**. Its coverage is the provided lines, not a claim of a complete restaurant stocktake. The recorded sheet hash/name anchors the reviewed source; it is not a cryptographic identity signature or proof the sheet is authentic.

The `/inventory/operations` screen and `backend/tools/inventory_pilot.py` CLI use ordinary authenticated, CSRF-protected APIs, never a migration or admin database connection. No automatic decision endpoint is offered by the CLI. Templates contain synthetic sample data only; an approved Burbank catalog and signed manual sheet have not been provided or imported.

## Protected evidence contract

`POST .../count-sessions/{session}/evidence?evidence_id={UUID}` accepts raw JPEG/PNG only from the assigned counter of a draft. A stable UUID permits retry without overwriting an object. Maximum input/output 5 MiB, decoded 16 million pixels, single frame, verified magic/MIME and complete image decode. Pillow 13.0.0 is pinned (the sole added backend dependency; [maintainer release](https://pypi.org/project/pillow/13.0.0/)). Only JPEG/PNG decoders are enabled. Re-encoding fresh RGB pixels strips EXIF/GPS, metadata and appended payload; SVG/HTML/HEIC/animation/corrupt images are rejected. Photos aid identification only; quantity is always entered and confirmed manually. Body limits also cover chunked requests (256 KB JSON), plus real Redis 20 uploads/user/location/minute and 200 stored upload records/location/day.

The private object-store adapter uses a persistent private filesystem volume, directory mode 0700 and object mode 0600, random scoped identities and exclusive no-follow writes. It has no static route, public bucket or client-selected filesystem path. API/worker/migrator images run as an unprivileged user. This adapter supports a single API instance and shared local volume; managed S3/Azure adapters, multi-host storage and object-store-provider certification are **not implemented**. Use encrypted storage and a scoped backup in a controlled single-host staging pilot, or review a managed private adapter before scaling.

`POST .../evidence/{id}/access` issues a 60-second HMAC access grant bound to evidence, user and current opaque session. `GET .../content` requires the live session, current authorization, RLS-visible parent, retention state and grant in `X-Evidence-Token`. Tokens never appear in URLs or application logs. Responses are private/no-store, nosniff and sandboxed, with integrity verification. Object previews are revoked on hide/background and after 60 seconds. Previously delivered bytes cannot be recalled from a recipient's device; managed-device policy and physical UAT remain necessary.

The manager-only, paginated `GET .../evidence?state=expired|held|active|deleted` queue supports daily retention review and tombstone erasure retries in the operations screen. `PATCH .../retention` requires approval permission, an audit reason and an aware deadline; retention may only extend, up to 365 days ahead. Hold/release is audited. Deletion is allowed only after retention expiration without a hold. `POST .../delete` first commits the access-revoking tombstone, then erases bytes; an erasure error returns 503 and is retried safely. Metadata/audit/count history remain. Operators must schedule expiry review/deletion through the API and investigate orphan files after failed/crashed uploads; automatic retention scheduling is not claimed.

Malware control: outside `development`/`test`, uploads fail closed unless an absolute `EVIDENCE_SCANNER_PATH` is configured. The clamscan-compatible executable runs without a shell, with a timeout, on sanitized private bytes. Infection, scanner failure, timeout or missing executable reject the upload and clean up the object. The runtime image does not bundle signatures or claim antivirus readiness. CI verifies image sanitization and scanner failure behavior; **successful real antivirus scanning/signature freshness remains unverified and is a pilot blocker**. The development Compose runtime intentionally uses sanitizer-only evidence, recorded as `sanitized_only`; do not label these objects malware-certified.

## Permission matrix

| Workflow | Employee | Assigned GM | Organization Owner |
|---|---|---|---|
| Assigned draft count/photo upload | Own assigned session | Own assigned session with count permission | Only if explicitly assigned count permission |
| Photo view | Own session only | Authorized location reports | Authorized organization locations |
| Opening proposal/catalog import/reconciliation | Denied | Authorized location | Authorized organization locations |
| Opening decision/count approval | Denied | Authorized location; independent | Authorized organization; independent |
| Photo retention/hold/delete | Denied | Authorized location | Authorized organization locations |
| Ledger/audit update/delete | Denied | Denied | Denied |

Permissions are database data, and revocation is resolved on every request and by PostgreSQL. Client navigation is not an authorization boundary. Raw app database credentials remain trusted server credentials; transaction-local context is established by authenticated server code, never supplied by a browser.

## Verification record

2026-11-05 refresh: the previous published 2D head `9d8dcf0f770b688f471eda325e39a1470aefee57` is being integrated with the latest verified 2C base `efe74a6b29609b2d26d9c3b5df4c73bee0dc361b`. The original integration and verification records below are historical. See `docs/issue-18-integration.md` for the dependency order, preserved changes and still-open pilot gates; fresh integration-head hosted outcomes are recorded on PR #9, not inferred from previous runs.

Issue #18 integration: the refreshed 2C dependency passed [run 41740256624](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41740256624) at `2f0ae6952150738460f7d3a1b5859faf8c8ef213` (73 backend tests, four WebKit scenarios and 18 Dev Agent tests; zero failures/skips). Only then was 2D reconciled. Native three-way merge was conflict-free; all five migration files and every existing 2D application/operational tool remain byte-for-byte unchanged. The workflow retains main's gate, queue and snapshot security regressions; the Decimal suite retains main's added case conversion regression. The current 2D run, exact head and results are recorded on PR #9; no future run is claimed successful here. See `docs/issue-18-integration.md`.

All verification records below predate this Issue #18 integration. Their pending/failed/superseded statements refer to the explicitly named historical commits and runs, rather than the current final-head acceptance status. Operational/manual pilot gates at the end remain applicable.

Local: Python imports/compilation, original migration hash checks, ten focused Decimal/image/private-store/migration-contract unit tests, frontend TypeScript, ESLint and production build executed successfully. Local Docker/PostgreSQL are unavailable; local collection/static checks are not PostgreSQL results. Historical runs (not final-head acceptance):

- [41720214486](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41720214486), `0a8db35be022c14c317954768c424083a5340b98`: **123 backend tests and 6 WebKit scenarios passed, zero failed/skipped**, including the expanded catalog import and reconciliation screens. Compose/privacy probes and Gitleaks passed. The CLI step failed because its response reader attempted JSON decoding of logout's successful empty HTTP 204 response after catalog preview. Handle 204 explicitly; the remaining CLI commands were not claimed passed in this run.


- [41719160454](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41719160454), `bd00ce768b092cab3b1e4fa2e50ef1fb51bb69fa`: **122 passed, 1 failed, 0 skipped** in backend; Compose and secret audit passed. The concurrent photo test started/stopped shared application lifespans per client, allowing one test client to close Redis during the other request. Keep the fixture's single application lifespan while retaining two concurrent real HTTP requests and all assertions. Newly extended UI/CLI journeys did not execute in this failed run. Test credential dataclass representations are also redacted to keep diagnostics from exposing ephemeral passwords.
- [41718348044](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41718348044), `0bac75435de277b147649ea18d25f18b3f58f67e`: all three jobs passed, including the actual Docker privacy-canary exclusion and UID-10001/mode-0600 private-volume write/read/erasure probes, 123 backend tests and the original six browser scenarios. This preceded the extended import/reconciliation UI and CLI journeys.


- [41713381757](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41713381757) was superseded/cancelled after the upload concurrency review; no complete acceptance claim.
- [41713544607](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41713544607), `dcea1724e2c370ff302de440a08f26360ad626ff`: Compose and Gitleaks passed; backend suite stalled because a test held a reader transaction while another connection attempted TRUNCATE. The run was superseded/cancelled, and no complete backend result is claimed. Split the reader/RLS checks from isolated administrator mutation checks.
- [41714311255](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41714311255), `e2b9d31188b5eefee8da41396447c267bb29d064`: **119 backend tests passed, 0 failed, 0 skipped**; actual legacy 0004 ledger/frozen report upgrade through 0005 and PostgreSQL backup/restore passed; frontend checks/build, Compose and Gitleaks passed; original four WebKit cases passed. Two new pilot WebKit cases failed at the refresh assertion because persisted `315.000000` was compared with literal `315`. Opening independence, photo upload/view and offline/reconnect had already executed. Changed the assertion to exact Decimal-value equivalence; the remainder of those scenarios was not claimed passed in this run.

Synthetic tablet screenshots were inspected. The previous sticky submit panel could cover quantity controls after scrolling, so it was made inline and a WebKit center-point visibility assertion was added.

[Run 41716166360](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41716166360) verified implementation commit **`0ef1b196f1d5569760160400e63da24fc9b78cc1`**. All three configured jobs succeeded on GitHub-hosted Ubuntu. Actual outcomes:

| Check | Executed result |
|---|---|
| Full backend/security suite with real PostgreSQL 16 and Redis 7 | **123 passed, 0 failed, 0 skipped**; includes unit and real database/API tests |
| Legacy `0001 -> 0004 -> 0005` upgrade | Succeeded; 0004 ledger hash/frozen report digest unchanged, then one independent -25 adjustment and final 315 |
| Migration through 0005 and database roles/RLS | Succeeded as `chubby_migrator`; integration/application proof used restricted `chubby_app`, no superuser/BYPASSRLS |
| PostgreSQL backup/restore | Succeeded on isolated synthetic CI data, with matching ledger/audit/opening/evidence metadata, ownership, forced RLS and missing-context denial |
| Opening/photo/unit/concurrency/permission/immutable-history regressions | Passed in the 123-test suite, including explicit zero, raw opening denial, cross-scope isolation, finite numeric values and TEMP-table spoofing |
| Frontend | Frozen-lock install, TypeScript, ESLint and production build succeeded |
| Existing WebKit tablet regressions | **4 passed, 0 failed, 0 skipped** (approval, reversal, rejection, four-eyes/Owner) |
| New WebKit pilot scenarios | **2 passed, 0 failed, 0 skipped**, portrait 768×1024 and landscape 1024×768; independent opening, double-tap protection, private photo upload/view, offline/reconnect, refresh, hold, count approval, logout/unauthorized redirect |
| Restricted-role browser ledger proof | Both new scenarios: approved opening **340**, physical count **315**, exactly one adjustment **-25**, final ledger **315**; one protected evidence record linked and held |
| Compose | Configuration/build/startup/migration, PostgreSQL/Redis/API/worker/web health checks, `/health`, `/ready`, unauthenticated **401**, frontend route smoke and graceful shutdown succeeded |
| Gitleaks | Current source tree and full reachable Git history executed: **no leaks found**; committed environment-file check passed |

[JUnit, two browser summaries and synthetic screenshots](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41716166360/artifacts/13271335918) expire after seven days. Fixtures, generated passwords, access tokens, private operational inputs, database dumps, image bytes from real restaurants and server logs are not uploaded. Earlier runs 41715493855 and 41715755789 were superseded/cancelled during review; they are not separate acceptance claims. One upstream AnyIO/Starlette deprecation warning remains; it did not skip or fail tests.

This report update adds explicit backend Docker context exclusions for private photos, dotenv variants, keys and local databases, plus synthetic canaries checked absent from the built image. It also adds a Compose-only private-volume permission probe (UID 10001, mode 0600, write/read/erasure). The refreshed verification also extends both tablet scenarios through the catalog preview/confirmation and manual reconciliation screens, and executes seven authenticated CLI commands (catalog preview/import/replay, bulk zero opening preview/proposal, listing and reconciliation) with private output reports and explicit logout. These added journeys must actually execute before being reported passed. The subsequent documentation/verification commit must also pass the complete workflow before being reported as the final head; the implementation proof above is explicitly pinned to its own SHA/run.

Required hosted checks include the full prior suite plus opening zero/duplicate/concurrency/four-eyes/stale conversion/RLS/immutable history, import validation/replay/atomicity, reconciliation, protected photo validation/auth/CSRF/retention/hold/erasure/rate/integrity checks; migration through 0005; isolated PostgreSQL backup/restore; TypeScript/ESLint/build; original four WebKit scenarios plus two opening/photo/retry/refresh/offline/logout tablet scenarios; restricted-role ledger verification; Compose startup/readiness/shutdown; pinned Gitleaks current tree/full history.

Physical iPad Safari UAT, independent external security review, real Burbank operational rehearsal against signed sheets, real antivirus success, encrypted evidence-volume recovery and actual staging deployment remain **UNVERIFIED**. Passing CI is not Issue #8 pilot sign-off. No production deployment or PR merge has occurred.

## Files changed in this draft

- `.env.example`
- `.github/workflows/sprint-1b.yml`
- `.gitignore`
- `backend/.dockerignore`
- `backend/Dockerfile`
- `backend/app/config.py`
- `backend/app/inventory_approvals.py`
- `backend/app/inventory_catalog_import.py`
- `backend/app/inventory_evidence.py`
- `backend/app/inventory_limits.py`
- `backend/app/inventory_pilot.py`
- `backend/app/inventory_units.py`
- `backend/app/main.py`
- `backend/migrations/versions/0005_inventory_pilot.py`
- `backend/requirements.lock`
- `backend/requirements.txt`
- `backend/tests/conftest.py`
- `backend/tests/seed_pilot_browser.py`
- `backend/tests/seed_pilot_upgrade.py`
- `backend/tests/test_inventory_counting.py`
- `backend/tests/test_inventory_evidence_unit.py`
- `backend/tests/test_inventory_pilot.py`
- `backend/tests/test_inventory_postgres.py`
- `backend/tests/test_inventory_units.py`
- `backend/tests/test_pilot_migration_contract.py`
- `backend/tests/verify_pilot_browser.py`
- `backend/tests/verify_pilot_cli.py`
- `backend/tests/verify_pilot_upgrade.py`
- `backend/tools/inventory_pilot.py`
- `backend/tools/verify_restore.py`
- `docker-compose.yml`
- `docs/examples/pilot-catalog.sample.json`
- `docs/sprint-2d-pilot-readiness.md`
- `docs/sprint-2d-pilot-runbook.md`
- `docs/sprint-2d-security-review.md`
- `frontend/app/inventory/approvals/page.tsx`
- `frontend/app/inventory/components/evidence.tsx`
- `frontend/app/inventory/operations/page.tsx`
- `frontend/app/inventory/page.tsx`
- `frontend/app/styles.css`
- `frontend/package.json`
- `frontend/tests/pilot-browser.mjs`
- `frontend/tests/smoke.mjs`
