# Controlled staging/pilot runbook — owner approval gates

No production deployment is authorized. This runbook prepares a single-host, isolated staging rehearsal. Physical iPad Safari UAT and independent review are mandatory before a real Burbank pilot. WebKit emulation is only an automated regression check. Keep real catalog sheets, device evidence and exports in ignored `pilot-private/` or an access-controlled document store, never the public repository or CI artifacts.

## Prepare and record

1. Record all four refreshed draft PR heads and exact CI URLs. Stack order is #3 (2A), #5 (2B), #7 (2C), then 2D. Rebase/retarget and rerun checks after each approved merge; merge only with explicit owner approval. Do not assume a previous stack head's CI proves a rebased head.
2. Assign an independent reviewer who did not author these changes. Use `sprint-2d-security-review.md`. Record findings, evidence, owner and resolution. This implementation's own inspection does not satisfy independent review.
3. Obtain an approved small Burbank SKU/category/zone/vendor list, explicit stock/purchase units and pack factors, signed opening sheet and named independent reviewer. Record source SHA-256 and approval reference. No approved operational data was available during implementation; sample JSON is deliberately labeled and is not a live seed.
4. Provision a separate PostgreSQL 16 database, restricted `chubby_app`, separate `chubby_migrator`, Redis 7, private persistent evidence volume, TLS ingress, encrypted disks/backups, managed secrets, correct HTTPS CORS/frontend origins and secure cookies. Bind database and Redis only to private networking. The supplied development Compose ports/HTTP configuration are not a staging ingress configuration.
5. Configure `EVIDENCE_STORAGE_DIR`, normal `EVIDENCE_RETENTION_SECONDS=2592000`, and a real absolute clamscan-compatible `EVIDENCE_SCANNER_PATH` installed in a reviewed runtime image. Supply up-to-date signatures, permission for the non-root API user, an approved test file and an infected-file rejection test; demonstrate success, rejection, timeout and unavailable-scanner behavior. No scanner is installed in the default runtime image. Keep uploads disabled until verification passes. JPEG/PNG only; iPad HEIC conversion and camera permissions need real-device validation.
6. Use invitation-only Owner, GM and Employee accounts scoped to Burbank. Have two independent reviewers for an opening created by the Owner or GM. Never put an admin/migration URL in the API environment or share an app database credential with an employee.

## Migrate and recover on isolated staging

- Take an encrypted PostgreSQL custom-format backup with the approved backup account and a consistent private-volume snapshot. Quiesce photo uploads/deletions while capturing both. Record checksums, time and backup permissions; do not log DSNs/passwords or upload backups as CI artifacts.
- Run `alembic upgrade head` with the migration-owner URL; record `alembic current` = `0005_inventory_pilot`. Original files 0001–0004 must match the pinned hashes in the regression test. Exercise the upgrade on a **copy at 0004** as well as a fresh database before staging approval.
- Restore into another isolated database/volume pair. Restore ownership to `chubby_migrator`, ACLs to `chubby_app`, forced RLS, triggers and grants. Compare immutable ledger/audit/opening records and evidence hashes/tombstones, test unknown context, then run the same restricted-role and authenticated workflows. The CI PostgreSQL restore rehearsal uses synthetic data and does not certify this paired staging backup.
- Check `/health`, `/ready`, role `chubby_app` with no superuser/BYPASSRLS, Redis ping, worker health, migration exit zero, frontend routes and unauthenticated 401. Record actual staging URLs privately, not credentials.
- Configure alerts for readiness failures, migration failure, API error rates, Redis rate-limit failures, disk/quota exhaustion, scanner rejection/error/timeout/signature age, pending byte erasure, missing/integrity-failed photo objects, stale ledger conflicts and backup/restore age. Restrict audit/log access. Log no cookie, CSRF token, grant header, reset/invite token or photo bytes. Verify TLS/proxy header redaction and JSON/upload size limits.

## Import an approved catalog

Use `/inventory/operations` or the authenticated CLI. The sample at `docs/examples/pilot-catalog.sample.json` illustrates the format only. Preview and inspect every row, normalized physical factor, zone, vendor, price and unit. Quantity, factor and price inputs are Decimal **strings**. `ea` can represent an explicitly reviewed item-specific package; there is no universal case/bag conversion. Do not disguise mass-to-volume factors without an approved per-item conversion.

Example CLI invocation (no credentials in shell arguments):

```sh
mkdir -p pilot-private
.venv/bin/python backend/tools/inventory_pilot.py \
  --base-url https://APPROVED-STAGING-API \
  --email gm@APPROVED-DOMAIN --location LOCATION-UUID \
  --action catalog-preview --input pilot-private/catalog.json \
  --output pilot-private/catalog-preview.json
```

Replace the visibly symbolic origin/account/location with approved values. The CLI prompts for a password, keeps cookies only in memory, signs out afterward and writes mode-0600 reports without overwriting files. Inspect the preview and manually create a commit input containing the same `rows`, returned `preview_digest`, a fresh `idempotency_key`, `confirmed: true` and approved `approval_reference`. Use `--action catalog-import` with that input. Imports are atomic and create-only. A duplicate matching idempotency key replays the original result. Corrections to live catalog/conversions require a separate reviewed change; do not mutate them ad hoc through SQL.

## Opening stock and rehearsal

1. Proposer compares each physical item and unit with the approved signed sheet. The opening workflow previews/records input quantity and converted stock quantity. Explicit zero requires the same independent confirmation as a positive opening. Missing baseline remains unknown.
2. For bulk proposals, preview `{"reason":"APPROVED-SHEET-REFERENCE","lines":[{"inventory_item_id":"ITEM-UUID","quantity":"0.340","unit_code":"kg"}]}`. Inspect preview; add its digest, a batch UUID key and `confirmed: true`, then record the batch. It posts proposals, not stock. Duplicate SKUs/items or invalid conversions must reject the whole batch.
3. An independent authorized GM/Owner reviews every proposed item, quantity, conversion and reason in the opening dashboard, then explicitly approves or rejects. The proposer cannot self-approve, including high-impact stock. No existing ledger activity is allowed. A wrong opening must be corrected with a fresh count and independent compensating count adjustment; history is never edited.
4. On sample isolated data, demonstrate approved opening 340 g, employee-confirmed count 315 g (with optional identification photo), immutable submission, independent GM approval -25 g, final ledger balance 315 g. Record one opening and one adjustment despite retry/double-tap. Compare both with the signed manual sheet.
5. Also exercise rejected count (zero posting), receipt recorded after submission (approval conflict, create a fresh count), and audited compensating reversal (original adjustment remains, current receipts retained). Never post a discrepancy automatically from the reconciliation tool or from an AI/photo inference.
6. Reconcile with `{"manual_sheet_sha256":"64-HEX-DIGEST","signed_by":"APPROVED-SIGNER","idempotency_key":"UNIQUE-KEY","lines":[{"sku":"APPROVED-SKU","quantity":"315","unit_code":"g"}]}`. Use screen or CLI `--action reconciliation`. Confirm matched/discrepancy/unknown-baseline for **all required catalog SKUs**; omitted items are not counted by this request. Record the sheet checksum and a human sign-off externally. A typed name/hash is not signature authentication.

## Evidence retention operations

Review expired objects through authenticated metadata and invoke delete after retention, without a legal hold. Record a reason. Tombstone and byte erasure must both succeed; alert/retry 503 erasure failures. Configure an approved external scheduler or an operator checklist for daily expiry review; this sprint does not silently create a schedule. Reconcile private object keys against DB metadata after crashes; quarantine unknown files before any owner-approved erasure. Never delete files directly to bypass hold/retention or erase database metadata. Audit legal hold placement/release. Verify retention policy against restaurant requirements before setting pilot accounts live.

## Physical iPad Safari UAT — UNVERIFIED

Record actual device model, iPadOS/Safari versions, date, employee/GM identities, orientation, evidence links and sign-off. Test portrait and landscape, touch targets/keyboard/scroll, camera permission allow/deny, JPEG/HEIC handling, manual quantity confirmation, evidence upload/view/hold, Wi-Fi loss before/during save/upload/submit/decision, reconnect/retry/double-tap, browser refresh, session expiry, invalid CSRF, login/logout and another employee's/cross-location denial. Confirm server results after every ambiguous network failure. Saved data persists; unsaved entries are not an offline synchronization feature. No physical-device result is inferred from Playwright.

## Stop, rollback and forward fix

Stop counting/decisions/uploads, revoke affected sessions/assignments and preserve logs/evidence if isolation, audit, ledger uniqueness or scanner/integrity checks fail. Disable pilot access without modifying history. Do not run a destructive Alembic downgrade (0004/0005 intentionally refuse it). Roll back application images only to a schema-compatible version after review; restoring an old database can discard later decisions and must include an owner-approved ledger reconciliation and corresponding evidence snapshot. Prefer a reviewed forward migration and compensating movement for stock corrections. Re-run all tests and independent review before reopening access. Never introduce automatic purchasing, Toast deductions or production deployment as part of recovery.

Pilot approval remains blocked until independent review, actual device UAT, approved Burbank catalog/manual-sheet rehearsal, real scanner verification, paired staging recovery, monitoring and owner sign-off are evidenced.
