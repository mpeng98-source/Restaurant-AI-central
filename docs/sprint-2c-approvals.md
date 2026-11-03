# Sprint 2C inventory decisions and corrections

Issue #6 extends Sprint 2B commit `076b8099ce398e8abda86e2f4e023414e040ec36` on `codex/sprint-2c-approvals`. Its draft PR targets `codex/sprint-2b-counting`; PR #3 and PR #5 remain unmerged dependencies. There is no production deployment.

## Approval semantics

The state sequence is `draft -> submitted -> under_review -> approved | rejected`. A submitted report must first enter review through the existing 2B endpoint. Final decisions require `inventory:approve` at the authorized location. Migration `0004_inventory_approvals` explicitly grants that permission to Corporate Owners; GMs already have it at assigned locations. Server authorization and PostgreSQL permission/assignment checks both apply.

Reviewers submit the current version, the server's SHA-256 digest of the entire frozen report, a reason, an idempotency key, and an accepted/disputed verdict for every frozen line. The digest includes the organization, location, assignee, cutoff, thresholds, line identities, counter identities and full snapshots. It excludes mutable review-state version; version is checked separately. Missing, duplicate, unknown or changed line identities cannot post.

Approval is atomic for the entire report. Every line must be accepted and have an initialized baseline; every counter must still hold an active location count assignment. No partial approval is supported. A mixed accepted/disputed review must be rejected as a whole or recounted in a new session. Rejection requires at least one disputed line, stores the complete review, closes the report, and posts zero stock movements. Rejection remains available when counter assignments or ledger state make approval unsafe.

Four-eyes control applies to final decisions and corrections: the assigned submitter and anyone attributed as a line counter cannot decide or reverse their own report, even after obtaining a GM role. A manager who created/assigned a session but did not count it may decide it. Reviewer identity is always taken from the authenticated session; request bodies cannot supply actors or organizations.

Counter identities also include immutable `inventory.count.line_saved` audit history. Overwriting or removing a draft line cannot erase an earlier counter's participation or allow that person to approve/correct the report. These historical counter identities are included in the reviewed digest and the dashboard.

## Exactly-once posting and ledger changes

The decision operation locks the report row and acquires the existing transaction-level organization/location ledger advisory lock. It validates the frozen digest, state and version, independent reviewer permission, and current counter assignments. Any movement recorded after the count cutoff for any counted item blocks approval, even when intervening movements net to zero. A changed current balance also blocks approval. The policy is conflict-and-recount, with no automatic rebase. Unrelated items do not invalidate a report.

A valid decision inserts one immutable session decision, an immutable per-line approval/rejection record, an append-only audit event, and one immutable `count_adjustment` for each approved nonzero variance. It then closes the session and increments its version. All work shares one database transaction: a failure on any line rolls back the decision, every movement, every line approval, the audit event, and the state transition. Zero variance closes an approved report without a zero-quantity movement. `baseline_required` lines cannot be approved; opening-balance initialization remains an explicitly managed prerequisite followed by a fresh count.

Unique report, line-approval, movement-approval and scoped idempotency constraints enforce exactly-once posting. Repeating the same request/key returns the stored decision, including after the version has advanced. Reusing the key with different inputs or attempting a second decision returns 409. Reasons and line choices are canonicalized before request hashing. Concurrent approval/rejection, duplicate taps and receipt/approval races are covered by real PostgreSQL tests.

Each posted adjustment records the decision, session source, count-line and approval identities, original cutoff, actor and approver, reason, balance before/after, and immutable audit reference. The original frozen snapshot remains unchanged.

The acceptance example is 500 opening + 200 receiving - 350 production consumption - 10 waste = 340 expected; a confirmed count of 315 produces -25 variance. A distinct authorized GM/Owner approval posts exactly one -25 adjustment, producing ledger balance 315.

## Corrections

Corrections add a new compensating movement referencing the original count adjustment. They never update or delete posted stock. A reviewer first requests a reversal preview containing the current balance and proposed signed compensation, enters a reason, and explicitly confirms it. The POST supplies the expected preview balance. Under the same location lock the database rechecks permission/four-eyes separation, compares current balance, and atomically creates one immutable reversal record, one +25 compensation for a -25 adjustment, and an audit event.

If a receipt changes 315 to 415 after preview, the stale preview returns 409. A refreshed correction adds +25 to 415, resulting in 440 and preserving the receipt. Repeated identical reversal requests return the existing record; a second key cannot compensate the same movement twice. Only count-adjustment reversal is exposed here. Reversals of reversals and arbitrary receiving/opening corrections require a separate reviewed workflow or fresh count.

The original decision remains approved with an explicit reversed movement trace. Its physical count and original -25 movement remain historical facts.

## API additions

All routes start with `/api/v1/inventory`. Existing secure session authentication is mandatory; every mutation also requires `X-CSRF-Token`. Organization and user IDs are server-derived.

| Method/path | Contract |
|---|---|
| `GET /locations/{location}/approval-dashboard?state=pending|reviewed|all&limit=50&offset=0` | Location approvers only; lists submitted/under-review or final reports. Limit 1–100. |
| `GET /locations/{location}/count-sessions/{report}` | Existing route now returns a decision summary to the assigned employee; authorized reviewers also receive digest, counter identity, blockers and movement/audit trace. |
| `POST /locations/{location}/count-sessions/{report}/decision` | `version`, `snapshot_hash` (64 hex chars), `action` (`approved`/`rejected`), nonblank `reason` (max 2,000 chars), `idempotency_key` (max 128), and `reviewed_lines: [{line_id, verdict: accepted|disputed}]`. Returns the current report and immutable decision. |
| `GET /locations/{location}/movements/{movement}/reversal-preview` | Independent location reviewer; returns current expected balance, compensation and proposed balance after. |
| `POST /locations/{location}/movements/{movement}/reverse` | `idempotency_key`, nonblank `reason`, `expected_balance` as a Decimal string. Returns the report, new compensating trace, and reversal ID. |

401 denotes missing/expired authentication; 403 denotes permission/CSRF/four-eyes denial; 404 denotes an inaccessible or absent report/adjustment; 409 denotes stale state, digest, baseline, assignment, ledger or idempotency conflict; 422 denotes malformed input. After 409, reload the report or reversal preview and review again. Rejected or stale counts are not edited back into draft: create an explicit fresh session.

## Database and RLS

Only `0004_inventory_approvals` is added. Migrations `0001`, `0002`, `0003` are preserved. New decision/reversal tables have forced tenant/location RLS, scoped composite foreign keys, unique idempotency keys, and mutation/truncate guards. The app role can only append through the validated paths. Per-line approvals are now append-only. Count/reversal ledger inserts require matching immutable records and metadata; direct forged adjustment or terminal-state writes fail. All functions run as the invoker with RLS; none use `SECURITY DEFINER` or `BYPASSRLS`.

The 2B session trigger remains responsible for drafts, submission and beginning review. A guarded terminal-transition trigger handles approved/rejected transitions only when nested within the validated decision operation. Existing movement immutability and posting-clock/advisory-lock guards remain active. Existing audit immutability is retained.

Migration 0004 is deliberately forward-only: removing financial history requires an explicitly reviewed corrective migration. Fresh migration-chain upgrade is verified in CI; a destructive downgrade is not claimed.

## Interface and browser verification

`/inventory/approvals` provides pending/reviewed filters, per-line expected/physical/variance/percentage/baseline information, counter identities, notes, evidence metadata and cutoff. Each line must be explicitly accepted/disputed; a reason and confirmation are required. Synchronous busy guards, disabled actions and stable request keys protect against duplicate taps. Four-eyes and stale-ledger blockers are visible. Employees can see their own final status/reason; they cannot use approval endpoints or read other employees' reports.

The interface supports portrait/landscape tablets with touch targets and wrapping audit identifiers. Correction controls show an explicit current-balance preview and reason/confirmation before compensation. Offline/unavailable and 409 responses are shown honestly; there is no offline synchronization. Photo upload/storage/retention is not implemented, and no upload control or public evidence URL is offered.

Playwright 1.64.1 and its core package are added as locked development dependencies solely for actual browser acceptance; existing dependency versions are retained. CI installs WebKit and runs four real PostgreSQL scenarios at 768×1024 and 1024×768 viewports with mobile/touch settings: approval, approval plus reversal, rejection, and four-eyes blocking followed by independent Owner approval. A restricted-role SQL check then verifies final balances and immutable adjustment quantities. This is browser/device emulation, not physical iPad or native Safari certification.

The browser server uses non-Secure cookies only for its isolated HTTP loopback test process. The existing application production-cookie validation is unchanged. Fixture passwords are random, stored in an ignored mode-0600 temporary file, redacted from browser errors, and never included in artifacts. Only JUnit, the browser summary, and screenshots are uploaded using the verified pinned `actions/upload-artifact` v4.6.2 commit, with seven-day retention. No credentials or browser traces are uploaded.

The PR and final report record actual hosted backend/browser counts, CI URL, Compose health/startup/shutdown, frontend checks and Gitleaks results. Evidence upload/storage/retention, physical-device acceptance and production deployment remain outside verified functionality.
