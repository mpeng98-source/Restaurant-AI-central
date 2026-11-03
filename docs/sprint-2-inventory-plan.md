# Sprint 2 — Inventory Agent Phase 1 implementation plan

**Issue:** #2  
**Branch:** `codex/sprint-2-inventory-agent`  
**Baseline:** `0ea3d2ad454811c38fb5e43da677a55d2d831824` (squash merge of Sprint 1B PR #1)  
**Deployment:** None. Development and pull-request verification only.

## Goal

Implement the first secure inventory workflow for Chubby Dumplings Burbank while preserving multi-tenant organization/location isolation. Employees count stock on iPads; the GM reviews discrepancies and approves adjustments; every approved stock change is an append-only ledger movement.

## Work packages

1. **Schema and RLS:** add Alembic `0002_inventory` (never edit applied `0001_foundation`); inventory categories/items, units and conversion factors, storage zones, vendor item references, count sessions/lines, stock movements and approval links. All location records must be scoped by organization and location, with restricted application role policies.
2. **Catalog APIs:** authorized CRUD for stock items and categories; stable SKUs/barcodes; separate raw ingredients, finished goods, packaging and sellable menu products; explicit purchase vs stock units and decimal-safe conversions.
3. **Count workflow:** employee starts assigned session, enters counts, notes and photo metadata, saves draft, submits once. Track server timestamps, count snapshot, counter and state transitions. The API must reject unauthorized locations and stale/duplicate submissions.
4. **Variance:** compute recorded ledger balance vs submitted physical quantity at a defined cutoff; distinguish uninitialized baseline from zero balance; configurable thresholds; no automatic ledger posting.
5. **GM approval:** review variance and count evidence; approve or reject with a reason. Approved adjustment creates exactly one idempotent ledger entry in a single database transaction; rejected adjustment creates none. Audit every decision.
6. **iPad-first frontend:** item search, count entry, clear units, optional photo upload and confirmation, draft/submitted indicators, variance review and GM approval. Show offline/unavailable state honestly; no implied offline synchronization unless implemented and tested.
7. **Tests and CI:** real PostgreSQL migrations, RLS, permission checks, transaction concurrency, idempotency, unit conversions, ledger immutability, frontend typecheck/lint/build and Compose runtime. Required integration tests must not be skipped in hosted CI.

## Data integrity requirements

- Store quantities with `NUMERIC` / Python `Decimal`, not binary floating point.
- Maintain base units and explicit conversion rules. Never automatically convert incompatible dimensions (pieces to weight) without an item-specific conversion.
- Ledger balances are derived from posted movements. Do not overwrite a balance as the primary source of truth.
- No destructive edits to posted stock movements; use compensating reversal movements with traceable references.
- Ensure approval posting is atomic, uses a unique idempotency key, and handles concurrent approvals.
- Distinguish physical count discrepancies from unrecorded receipts, production, waste or POS consumption. No Toast sales sync is available in this sprint.
- Photo recognition is assistive only; employee confirms item identity and quantity. Protect photos with tenant/location-scoped access, upload validation and retention controls.

## Role model

- Corporate Owner: authorized organization-level visibility and configuration; approvals only when explicitly permitted.
- GM: location-scoped count review and adjustment approval.
- Employee: assigned-location inventory counting, no approval/posting.
- AI: read-only anomaly summaries and proposed actions; no direct inventory writes.

## Delivery milestones

- **2A — Schema + ledger:** migration, models, RLS, conversion utilities, security tests.
- **2B — Counting + variance:** APIs, session state machine, concurrency/idempotency tests.
- **2C — Approval + UI:** GM approvals, employee iPad flows, evidence handling.
- **2D — Hosted verification:** CI, Compose, acceptance evidence, documentation and PR.

## Acceptance scenarios

1. Opening stock of 500 pieces plus 200 received minus 350 consumed and 10 wasted yields expected 340 pieces. A physical count of 315 shows -25 variance; no stock change occurs until GM approval.
2. GM approval posts a -25 adjustment exactly once, including under retries and concurrent requests; rejection posts no movement.
3. Unauthorized employees cannot access another location or another organization's stock; attempts fail at API and PostgreSQL RLS layers.
4. Counts cannot use invalid units, negative quantities (unless explicitly supported by a justified workflow), or silently overwrite newer submissions.
5. A count with no initialized stock baseline is marked `baseline_required`, not interpreted as zero expected inventory.
6. Required tests pass with zero skips on GitHub Actions. No production deployment.

## Scope exclusions

No automatic purchasing, vendor portal submission, invoice reconciliation, Toast integration, camera-based quantity estimation, employee discipline, or production deployment.

## Development instructions for Codex

Read `AGENTS.md`, `docs/security-model.md`, the existing migrations, authentication and authorization modules before coding. Implement work packages incrementally on this branch. Open a draft PR for review after the first coherent tested slice. Do not merge or deploy without owner approval.
