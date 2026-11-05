# Separate AI review: inventory platform

Date: 2026-11-05. **This is AI review, not independent human approval.** Under the owner's subsequent synthetic internal-demo scope, AI review plus confirmed-finding remediation and relevant tests is the required demo review standard; independent human sign-off is not required for the demo. It remains a future live-pilot requirement. The separate read-only AI security reviewer found no confirmed exploitable vulnerability in the inspected versions. That is a bounded review result, not proof of security. The implementation agent then confirmed and fixed request-validation defects; these are not demonstrated authorization bypasses.

## Reviewed versions and scope

- PR #56: `c027e84689b900d8fe1408d799c8a0e2554a0478`.
- PR #7: `efe74a6b29609b2d26d9c3b5df4c73bee0dc361b`.
- PR #9: `5ec312eff03b8cb95184a69434d9bfc648a3fd47`.
- Main: `d5fb06c24e94305c09f78bd0f719554a6853425f`.

Read-only review covered authentication/session/CSRF, server-derived tenant/location permission checks, transaction-local PostgreSQL context and forced RLS/restricted application roles, approvals/four-eyes/idempotency/concurrency, immutable audits/ledger, private photo scope/access/retention/scanner failure handling, forward-only migrations and documented recovery. Existing negative and concurrency tests were inspected by the reviewer; they were not executed by that reviewer. Post-fix hosted runs below are actual execution evidence.

Use the [reviewer/owner handoff](reviewer-owner-handoff.md) for version-pinned source documentation and human-review requirements, the [completion plan](platform-completion-plan.md) for branch progress, and the pilot runbook/security self-review linked from the handoff for operational procedures. Original handoff SHAs remain the historical pre-fix snapshot.

## Confirmed validation findings

| ID | Severity | Exact reviewed source | Impact | Reproduction and regression evidence |
|---|---|---|---|---|
| V1 | MEDIUM correctness; no demonstrated security bypass | `backend/app/inventory_counts.py:20-53` at PR #56 reviewed SHA; also inherited by #7/#9 | Pydantic defaults silently ignore extra fields. A misspelled threshold is discarded and default 5% is used; an assignment request can reset a intended threshold to its default. Unknown count-line/version fields also appear accepted. | Before fix: `CreateSession.model_validate({"idempotency_key":"synthetic-key","percentge_threshold":"25"}).percentage_threshold` yields Decimal 5 rather than rejecting. After fix, all create/assignment/line/version models raise `extra_forbidden`; authenticated API tests send misspelled thresholds and unknown line/submit fields, require HTTP 422 and verify unchanged version, empty lines, draft status and only the original creation audit. Correctly spelled explicit 25 and omitted default 5 remain supported. |
| V2 | LOW contract correctness; no demonstrated security bypass | `backend/app/inventory_approvals.py:21-32,49-52` at PR #7 reviewed SHA; also present in #9 | Decisions and nested reviewed lines ignore unknown fields; reversal inherited the permissive Decimal model. Additional input could be accepted without being part of the recorded decision contract. Required action/verdict/four-eyes controls still apply. | Before fix: a valid decision with top-level `confirmed:true` or a reviewed line with `approved:true` validates and discards those fields. Post-fix unit tests require rejection at top level and nested line, plus direct reviewed-line/reversal rejection. Authenticated decision regression verifies HTTP 422, unchanged 340 balance, no decision row, then normal valid approval succeeds exactly once. |

Fixes use the existing Pydantic `ConfigDict(extra="forbid")` prior art already used in pilot opening/reconciliation/catalog/retention/delete models. Count Decimal/version bases are strict, and approval decision/reviewed-line models are explicitly strict. No migration, authentication/authorization, RLS, ledger/audit trigger, runtime permission, workflow/gate or dependency change was made. Intentional API behavior change: unknown fields now return 422; clients must correct typos rather than rely on discarded input. Known fields, omitted defaults, exact Decimals and binary-float/nonfinite rejection are preserved.

## Post-fix verification

Count fix on PR #56: `fb4708f5009856071cd70289ad049fa7ab58da08`. Local non-root verified devcontainer ran 11 focused count-request/Decimal tests successfully. Hosted runs [42089268100](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/42089268100) and [42089268124](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/42089268124) both succeeded on that head: 54 backend tests and 22 frontend regressions, zero failures/skips.

Approval branch contains the same count fix plus strict decisions/reviewed lines at `ac7a57aa71f672ea6c83f32621e0c201b19d51f0`. Local non-root devcontainer ran nine strict count/approval validation tests successfully. Hosted [42089913200](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/42089913200) and [42089913594](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/42089913594) succeeded: five checks, 83 backend tests and four WebKit scenarios, zero failures/skips. Authenticated PostgreSQL regressions executed the unknown-field cases and valid posting checks.

Pilot integration head `3f94052b677cc7e0260f750f238cc0072d349732` has the prior pilot head first and verified approval fix second. The native merge was conflict-free and changed only the two request-model files and four related test files. All five migrations and other application/operational code are unchanged. Hosted [42090636367](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/42090636367) and [42090636282](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/42090636282) succeeded: five checks, 134 backend tests, six WebKit scenarios and seven authenticated CLI commands, zero failures/skips. The suite includes real PostgreSQL/Redis, legacy migration integrity, synthetic database recovery, frontend checks/build, Compose/privacy probes and secret scans. Browser emulation and synthetic recovery do not close operational gates.

## Limits and open gates

No independent human sign-off is supplied. No physical iPad Safari/camera/network-loss test, real scanner/signature verification, approved restaurant catalog/opening/manual-sheet rehearsal, paired staging database/private-photo recovery, operational alerts/load acceptance or SMTP delivery was performed by this review. Existing CI uses synthetic data and browser emulation. The filesystem evidence adapter remains single-host; host/migration administration is trusted and audit immutability is not WORM certification. No automated restaurant action, merge or deployment is authorized.

## Future live-pilot owner checklist (not demo requirements)

For the current synthetic demo, use the [demo checklist](reviewer-owner-handoff.md#current-owner-scope-synthetic-internal-demo). The actions below are only for a separately approved live-restaurant scope. Merge/deploy authorization remains separate in either case.

1. Assign an independent human security reviewer; send the handoff and this AI report, including both original and fixed versions. Require a dated findings/retest/approval report.
2. Assign an operations engineer and approve a controlled non-production environment, scope/budget and least-privilege secret delivery separately. Require real scanner and paired database/photo recovery evidence.
3. Decide photo retention/holds/device handling and single-host pilot suitability; name the daily operator and alert recipient.
4. Provide approved catalog/units/conversions, signed opening/count sheets, a human counter and a different authorized approver. They, not the AI, confirm stock and decisions.
5. Provide the actual iPad and employee/GM testers for the runbook's Safari/camera/network/auth-expiry tests; keep failed or missing cases open.
6. Review final refreshed versions and independent findings before separately authorizing any code merge (#7 before #9; completion-plan overlap must be preserved). Later pilot and production decisions are separate. Nothing in this AI report closes those gates.

## Private internal-deployment preparation: AI engineering delta review

The deployment-preparation agent subsequently found and fixed the following defects through configuration inspection and hosted synthetic execution. This is **AI engineering review**, not another independent reviewer or human sign-off. It does not alter the bounded original review above.

| ID | Severity | Exact affected source | Impact and reproduction | Fix and executed regression |
|---|---|---|---|---|
| D1 | MEDIUM private-access configuration | `ops/demo/Caddyfile:2-3,9-14` at `a05bcc5f1b72d56078ee26b0d0231c3900ce434e` | Caddy sorts `handle` before a standalone `respond`. `caddy adapt` placed both proxies ahead of the tester-IP 403 response; hosted disallowed-source verification failed. The intended IP perimeter was ineffective; authentication remained enforced. No cloud deployment existed. | An ordered `route` places denial before every proxy. At `3ee3d2e9e33bbeb13e7fb273fe2d837bdeb3635a`, the dedicated [hosted rehearsal](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/42108729359) passed denial for both `/` and `/api/v1/me`, then allowed-source acceptance and restart. |
| D2 | LOW availability/configuration | `ops/demo/redis-start.sh:8-10` at `1c1ba72fcd2a589a56db9b9b9d1fceafe545e676` | Root rewrote a Redis-owned file under sticky `/tmp` on restart, incompatible with protected-regular-file hardening. Initial hosted startup worked but Redis became unhealthy after restart. This host's protection was 0, so its earlier local restart did not establish hardened-host behavior. | Configuration moved to a private 0700 `/run/chubby-redis` directory with a 0600 file. The same hosted rehearsal passed startup, permission checks, authenticated Redis health and whole-stack restart with `fs.protected_regular=2`, verified in its downloaded report. |

Downloaded `internal-demo-verification` reports name that exact fixed SHA and verify synthetic Owner/GM/Employee HTTPS login/secure cookies, location/tenant denials, independent opening/count approval and replay, scanner-less upload 503, unchanged decision/movement/audit references after restart, and identical digests for two ledger rows and ten location-scoped inventory/demo audit rows. The trusted certificate is a disposable internal CA, **not public HTTPS**. The broader existing browser job is tracked separately in the [deployment evidence](internal-test-deployment.md#current-limitations-and-evidence); this successful dedicated job is not a claim that every job finished.

AWS IAM/metadata isolation, real public HTTPS/firewall, boot-time secret retrieval, actual host reboot and operational backup/rollback remain unverified until separately authorized hosting execution. No live data, merge, resource purchase or deployment is authorized by these findings.
