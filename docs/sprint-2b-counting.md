# Sprint 2B inventory counts

Issue #4 builds on PR #3 at `858cd7e12de2b544a543107dabb9e6906637818d`. The branch is `codex/sprint-2b-counting`; its pull request targets `codex/sprint-2-inventory-agent`. Neither PR is merged by this work.

## Data and state transitions

Migration `0003_inventory_counting` adds the assigned employee, storage zone, version, submission cutoff and variance thresholds to count sessions; count lines gain counter attribution and a frozen JSON snapshot. It leaves `0001_foundation` and `0002_inventory` unchanged. The preceding inventory metadata remains separate from foundation metadata because `0001` creates its known foundation tables dynamically.

A session has one assigned counter and follows `draft -> submitted -> under_review`. Only that employee can edit or submit, and only while their active location assignment grants `inventory:count`. Assignment eligibility follows the location-assignment records; it does not require a separate employee profile per location. The existing login checks still require an active user. Permissions from multiple valid roles at the requested location are combined. Managers with inventory review permission can create, reassign and configure a draft, then begin review after submission. Owners can review organization locations through the existing server-derived organization grants. No approval or stock-posting endpoint exists in 2B.

Every draft edit, line removal, reassignment and transition requires the current session version and increments it. A row lock serializes edits. A stale version or repeated submission returns HTTP 409. A second counter cannot edit the same session: managers must reassign it first, immediately revoking the previous counter's access. Reassignment retains draft lines with their individual counter attribution. The new assignee reviews those lines before submitting. Lines are unique per session/item; editing replaces that draft line, never adds a duplicate. Drafts have no time-based expiry; expected stock is calculated at submission, not session creation.

If a saved item's enabled status or unit configuration becomes invalid before submission, the database rejects submission atomically and the API returns 409. The session stays in draft with its previous version and lines; no partial snapshot or stock change is committed.

The create-session idempotency key is unique per organization/location. Replaying an identical visible request returns the original session; conflicting reuse returns 409. The interface retains a creation key across an uncertain network response. Submitted lines are immutable at API and database trigger/RLS layers. A submitted session can only advance to `under_review` in this phase.

## API contract

All routes below start with `/api/v1/inventory`. All require the existing secure session cookie. Every mutation also requires `X-CSRF-Token`. The server resolves organization and location access from the principal; request bodies do not accept an organization ID. Quantities and thresholds must be Decimal strings, with up to six decimal places. JSON binary floating-point values are rejected.

| Method and path | Contract |
|---|---|
| `GET /locations` | Locations accessible through inventory permissions; includes `can_count` and `can_review`. |
| `GET /locations/{location}/catalog` | Active enabled items, SKU, stock unit, allowed physical/item-specific units and zones. |
| `GET /locations/{location}/assignees` | Reviewers only: people with active location assignments and count permission; profile names are shown only when authorized. |
| `GET /locations/{location}/count-sessions?limit=50&offset=0` | Assigned employee's sessions, or all location sessions for reviewers. Limit 1–100. |
| `POST /locations/{location}/count-sessions` | `idempotency_key`, optional `assigned_to` (defaults to self), `storage_zone_id`, `quantity_threshold` (default `"0"`), `percentage_threshold` (default `"5"`). Assignment/threshold configuration requires reviewer permission. |
| `GET /locations/{location}/count-sessions/{session}` | Session, version, state and lines. Variance snapshots are returned only to reviewers. |
| `PATCH /locations/{location}/count-sessions/{session}` | Reviewer-only draft assignment/configuration: `version`, `assigned_to`, optional zone, quantity and percentage thresholds. |
| `PUT /locations/{location}/count-sessions/{session}/lines/{item}` | Assigned counter: `version`, exact `sku`, nonnegative `quantity`, `unit_code`, optional `note` (max 2,000 chars) and `photo_object_key`. |
| `DELETE /locations/{location}/count-sessions/{session}/lines/{item}?version=N` | Remove an assigned counter's draft line. |
| `POST /locations/{location}/count-sessions/{session}/submit` | Assigned counter: `version`. Requires at least one saved line. Freezes all saved count evidence and variance in one transaction. |
| `GET /locations/{location}/count-sessions/{session}/variance` | Reviewer-only frozen report after submission. |
| `POST /locations/{location}/count-sessions/{session}/review` | Reviewer-only: `version`; changes `submitted` to `under_review`. Posts no movements. |

Successful mutations return the current server session, version and saved lines. Typical failures are 401 (no valid session), 403 (permission/location/CSRF), 404 (session hidden by assignment/RLS), 409 (stale version/state/idempotency), and 422 (invalid quantity, SKU, unit, assignment, zone or empty submission).

`photo_object_key` is optional opaque metadata for a future protected evidence service and must begin with `{organization_uuid}/{location_uuid}/`. This phase neither uploads nor fetches objects. The UI has no upload control.

## Variance and cutoff

Submission takes the same transaction-scoped PostgreSQL advisory lock used by ledger inserts for that organization/location. New ledger postings receive the database's `clock_timestamp()` after obtaining that lock, preventing caller backdating. Submission sets a database-generated cutoff and reads committed ledger movements visible at that cutoff. Snapshot JSON stores the item name/SKU, entered quantity/unit, counter, notes/photo key, exact conversion factor, normalized stock quantity, expected stock, variance, percentage, status and explanation. Later receipts or catalog/conversion changes cannot change this frozen report.

Normalized quantity uses explicit item-specific factors when configured; otherwise it uses the global factors for compatible dimensions. Incompatible dimensions without an item-specific factor are rejected. The normalized result rounds to six decimal places using PostgreSQL numeric rounding; binary floating point is not used.

Expected stock is the sum of signed immutable movements. An `opening` movement or approved `count_adjustment` establishes a recorded baseline. Receipts alone do not establish a complete baseline. Without one, the report is `baseline_required`, and expected/variance/percentage are null. An initialized zero expected balance has a defined quantity variance but a null percentage. Otherwise percentage is `variance / abs(expected) * 100`. A discrepancy is `above_threshold` if either absolute quantity or absolute percentage exceeds its configured threshold; otherwise it is `within_threshold`. The quantity threshold applies in each item's stock unit.

Example: 500 opening + 200 receiving - 350 production consumption - 10 waste = 340 expected. Confirming 0.315 kg for a gram-based item gives 315 g, variance -25 g and -7.352941%. Submission and review do not create approval rows or ledger movements.

## Security and interface

Forced RLS remains enabled. Count policies additionally require the assigned counter or server-derived review permissions, with independent organization/location checks. Read/write membership checks derive from active database assignments and role permissions. Database triggers validate session transitions, versions, zone/item membership, units, actor attribution, and frozen snapshots. The restricted `chubby_app` role cannot delete/truncate sessions or mutate posted movements. Ledger immutability and the 2A approval guard remain active.

The `/inventory` screen is responsive for portrait/landscape iPads, uses controls at least 48px high, and provides item/SKU search, explicit units, notes, individual saves, session history, assignment/threshold configuration, submission and read-only review. Unsaved entries must be saved before submission. Offline/unavailable and HTTP 409 states require reconnection/reload; there is no offline persistence or background synchronization. Browser refresh can lose unsaved local input. Session lists use a paginated API; the initial UI lists the latest 50 sessions.

## Verification and Sprint 2C

The mandatory hosted workflow runs real PostgreSQL integration tests using `chubby_app`, migrations using the separate migration owner, zero-skip validation, frontend typecheck/lint/build, Compose health/startup/shutdown and frontend route smoke checks, plus pinned Gitleaks tree/history scans. The final report/PR records the actual run and counts.

Sprint 2C still needs approval/rejection, atomic exactly-once adjustment posting and reversal review, evidence upload/storage/retention, and full browser-driven iPad workflow acceptance. No Toast sales integration, automatic purchasing, vendor automation, production deployment or PR merge is part of 2B.
