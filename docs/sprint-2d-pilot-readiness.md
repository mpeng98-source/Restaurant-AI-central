# Sprint 2D — implementation and verification record

Issue [#8](https://github.com/mpeng98-source/Restaurant-AI-central/issues/8). Exact parent: `00b8f33bfdf354aab6838495ae5d0f162aa7d9ec` (PR #7). Branch `codex/sprint-2d-pilot-readiness`; draft target `codex/sprint-2c-approvals`. No merge or production deployment is authorized. The earlier 2C report describes the capabilities at its own commit; this increment adds the opening and evidence workflows that it identified as missing.

## Database and API contracts

Migration `0005_inventory_pilot` follows 0004. Files 0001–0004 are byte-for-byte unchanged; a regression test pins their SHA-256 hashes. 0005 is forward-only, as financial history and evidence tombstones must survive a rollback of application code. It adds:

- Immutable opening requests, frozen item/name/SKU/unit/factor/quantity, and immutable independent opening decisions. Both are tenant/location scoped, forced RLS, security-invoker triggers/functions. Creation requires `inventory:catalog:manage`; decision requires `inventory:approve`. Proposer and reviewer must differ, including Owner proposals; the proposer must retain permission at approval. All sizes require two people, covering high-impact openings without inventing a financial threshold.
- One immutable nonzero `opening` movement after approval; explicit zero is an approved baseline record with **no zero-valued movement**. Missing baseline stays unknown. Approval is rejected if any ledger activity or approved opening already exists, or the reviewed catalog changes. Location advisory locks serialize opening requests, decisions, regular movement posting and count submission. Duplicate matching requests/decisions replay the same identity; changed inputs conflict. Competing decisions cannot double-post. Raw opening inserts are rejected even when the caller supplies plausible metadata.
- Explicit zero baseline recognition in the replacement count snapshot function. Existing cutoff, Decimal arithmetic, frozen snapshots, independent count decisions, receipt-conflict detection, compensating reversals and immutable audits remain enforced. Incorrect openings are corrected by a fresh physical count and independent adjustment review; they are never edited or deleted.
- Private evidence metadata, immutable identity/hash/size/scanner provenance, scoped parent session, retention deadlines, legal hold and permanent deletion tombstones. A count line may reference only live protected evidence belonging to that same session. Audit records cover uploads, lifecycle changes, grants, views and byte erasure.
- Immutable catalog import, bulk-opening and manual-reconciliation operation records with idempotency fingerprints and audits. Restrictive policies additionally require catalog permission for catalog writes and approval/catalog permission for ledger inserts. Employee context cannot write catalog data or directly post movements.

Opening endpoints: `GET/POST /api/v1/inventory/locations/{location}/openings`; `POST .../openings/{request}/decision`; `POST .../opening-import/preview` and `POST .../opening-import`. Inputs require explicit confirmation, Decimal strings, reason and idempotency key. Bulk preview is digest-bound, bounded to 200 unique items, revalidated under lock, and imports proposals atomically. Each proposal still needs an independent decision.

Operational endpoints: `POST .../catalog-import/preview`, `POST .../catalog-import`, `POST .../reconciliation`. Catalog imports are create-only, 200 rows maximum, all-or-nothing, with a preview digest and human approval reference. They create categories, zones, ingredient items, enabled location records, vendors, mappings and explicit pack conversions. Global physical factors cannot be overridden. Existing SKUs/conversions are never silently changed. Reconciliation normalizes signed manual sheet lines, compares the committed ledger under the posting lock, reports unknown baselines and differences, and records **zero movements**. Its coverage is the provided lines, not a claim of a complete restaurant stocktake. The recorded sheet hash/name anchors the reviewed source; it is not a cryptographic identity signature or proof the sheet is authentic.

The `/inventory/operations` screen and `backend/tools/inventory_pilot.py` CLI use ordinary authenticated, CSRF-protected APIs, never a migration or admin database connection. No automatic decision endpoint is offered by the CLI. Templates contain synthetic sample data only; an approved Burbank catalog and signed manual sheet have not been provided or imported.

## Protected evidence contract

`POST .../count-sessions/{session}/evidence?evidence_id={UUID}` accepts raw JPEG/PNG only from the assigned counter of a draft. A stable UUID permits retry without overwriting an object. Maximum input/output 5 MiB, decoded 16 million pixels, single frame, verified magic/MIME and complete image decode. Pillow 13.0.0 is pinned (the sole added backend dependency; [maintainer release](https://pypi.org/project/pillow/13.0.0/)). Only JPEG/PNG decoders are enabled. Re-encoding fresh RGB pixels strips EXIF/GPS, metadata and appended payload; SVG/HTML/HEIC/animation/corrupt images are rejected. Photos aid identification only; quantity is always entered and confirmed manually. Body limits also cover chunked requests (256 KB JSON), plus real Redis 20 uploads/user/location/minute and 200 stored upload records/location/day.

The private object-store adapter uses a persistent private filesystem volume, directory mode 0700 and object mode 0600, random scoped identities and exclusive no-follow writes. It has no static route, public bucket or client-selected filesystem path. API/worker/migrator images run as an unprivileged user. This adapter supports a single API instance and shared local volume; managed S3/Azure adapters, multi-host storage and object-store-provider certification are **not implemented**. Use encrypted storage and a scoped backup in a controlled single-host staging pilot, or review a managed private adapter before scaling.

`POST .../evidence/{id}/access` issues a 60-second HMAC access grant bound to evidence, user and current opaque session. `GET .../content` requires the live session, current authorization, RLS-visible parent, retention state and grant in `X-Evidence-Token`. Tokens never appear in URLs or application logs. Responses are private/no-store, nosniff and sandboxed, with integrity verification. Object previews are revoked on hide/background and after 60 seconds. Previously delivered bytes cannot be recalled from a recipient's device; managed-device policy and physical UAT remain necessary.

`PATCH .../retention` requires approval permission, an audit reason and an aware deadline; retention may only extend, up to 365 days ahead. Hold/release is audited. Deletion is allowed only after retention expiration without a hold. `POST .../delete` first commits the access-revoking tombstone, then erases bytes; an erasure error returns 503 and is retried safely. Metadata/audit/count history remain. Operators must schedule expiry review/deletion through the API and investigate orphan files after failed/crashed uploads; automatic retention scheduling is not claimed.

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

Local: Python imports/compilation, original migration hash checks, Decimal unit tests, frontend TypeScript and ESLint executed successfully. Local Docker/PostgreSQL are unavailable; local collection/static checks are not PostgreSQL results. Hosted results and any failed attempts will be recorded after actual execution.

Required hosted checks include the full prior suite plus opening zero/duplicate/concurrency/four-eyes/stale conversion/RLS/immutable history, import validation/replay/atomicity, reconciliation, protected photo validation/auth/CSRF/retention/hold/erasure/rate/integrity checks; migration through 0005; isolated PostgreSQL backup/restore; TypeScript/ESLint/build; original four WebKit scenarios plus two opening/photo/retry/refresh/offline/logout tablet scenarios; restricted-role ledger verification; Compose startup/readiness/shutdown; pinned Gitleaks current tree/full history.

Physical iPad Safari UAT, independent external security review, real Burbank operational rehearsal against signed sheets, real antivirus success, encrypted evidence-volume recovery and actual staging deployment remain **UNVERIFIED**. Passing CI is not Issue #8 pilot sign-off. No production deployment or PR merge has occurred.
