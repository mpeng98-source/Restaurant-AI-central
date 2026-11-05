# Reviewer handoff and owner checklist

**Latest hosting revision:** the owner stopped AWS setup and confirmed no account,
SSO, domain or fixed tester IPs exist. Start with [the hosting comparison and
beginner account steps](hosting-choice.md), not the historical provisioning
approval below. No cloud resources exist. Private-tailnet transport is prepared
but unverified end to end, and current checkout costs could not be verified
because official pricing sites were unreachable.

## Current owner scope: synthetic internal demo

On 2026-11-05 the owner limited current work to an **internal, noncommercial demo with synthetic data and test accounts**. Independent human security sign-off is **not required for demo acceptance**. Use AI code review, fix confirmed findings and run relevant tests; see [the current demo acceptance and next steps](platform-completion-plan.md#current-internal-demo-acceptance) and [AI review/fixed findings](platform-ai-review.md).

This scope decision supersedes any blanket human-review or real-resource prerequisite in the historical handoff below for the demo only. Sections 3 and 4 are a **future live-restaurant review brief and gate register**, not demo blockers. Their independent review, physical devices, real restaurant sheets, scanner certification and paired staging recovery requirements remain applicable only if a live pilot is later authorized. Do not hire reviewers, buy services, grant access or provide private restaurant data merely to complete this demo.

Authentication, CSRF, tenant/location isolation, restricted-role PostgreSQL RLS, immutable audit/ledger history, independent proposer/approver controls and human stock confirmation remain required. AI cannot approve restaurant actions. Demo actors can be synthetic users but must exercise the same permission and approval paths.

**Private deployment update:** the existing feature branches are combined on `codex/internal-demo-deployment`, with a synthetic banner, private HTTPS Compose configuration, managed-secret setup and one-time test accounts. See the [deployment package, actual evidence and current owner checklist](internal-test-deployment.md); its current-version results supersede historical deployment assumptions below. No cloud service, URL, public certificate, firewall, AWS access, reboot recovery or operational rollback has been verified yet.

**Subsequent owner authorization (2026-11-05):** AWS EC2 hosting and private synthetic deployment are approved at $50–60/month, conditional on remaining checks and scoped access. No merge or live pilot is authorized. No resources are provisioned; AWS access, hostname and tester IP scope are still needed, and cloud/recovery gates remain open.

**Operator handoff ready:** verified candidate `d64881aee6e09f990d57e54c1e083584bf575de2` passed all five hosted jobs, 155 backend tests, six WebKit cases and seven CLI commands. The owner chose operator-executed deployment. Use [the final evidence, approved budget, secure setup and operator message](internal-test-deployment.md#final-hosted-verification); the operator must obtain actual cloud/DNS/tester resources and return verified results before a test URL is claimed. No human security reviewer hire is required for this demo.

Component heads rechecked on 2026-11-05: [#56](https://github.com/mpeng98-source/Restaurant-AI-central/pull/56) `5570503ed2abcefb7d0da0ee5134529e34cf2a28`; [#7](https://github.com/mpeng98-source/Restaurant-AI-central/pull/7) `ac7a57aa71f672ea6c83f32621e0c201b19d51f0`; [#9](https://github.com/mpeng98-source/Restaurant-AI-central/pull/9) `3f94052b677cc7e0260f750f238cc0072d349732`. All remain draft/open/unmerged; #9 still targets #7. The recommended eventual #56, #7, #9 integration order below is unchanged. No PR is currently open for the combined deployment branch; it can be tested and separately approved by exact SHA without merging any PR.

**Demo owner checklist**

1. Keep the demo synthetic and internal; do not supply real employee data, stock sheets, production credentials or live accounts.
2. Engineering can combine the existing branch features, add visible simulation labels and verify a test-account walkthrough without independent human sign-off. Review the resulting exact-version AI findings and test evidence; no new features or paid services are implied.
3. Treat WebKit/device emulation, sanitizer-only test photos and synthetic recovery as exactly that. Physical-camera behavior, actual antivirus, external SMTP and live staging remain unverified unless separately demonstrated.
4. Private EC2 deployment is now separately approved at $50–60/month through a cloud operator. Code merge, live restaurant use and production deployment remain unapproved; the earlier demo scope change alone did not authorize them.
5. Only if moving to a live restaurant later, use the future-live checklist below to assign reviewers/operators, approve policy/resources and close real operational gates.

GitHub state checked on **2026-11-05 at approximately 18:38 UTC**. This is a review package, not permission to merge, deploy, buy services or grant access. No credentials, private restaurant catalog, photographs, real account identities or backups belong in this document or public CI artifacts.

**Subsequent AI-review update:** see [the separate AI review and validation findings](platform-ai-review.md) for the original reviewed SHAs, exact affected lines, reproduction cases, fixed branch versions and post-fix evidence. The snapshot below predates those fixes. This AI review does not supply independent human approval. Review the fixed versions and any subsequent changes before approving integration.

## 1. Versions, dependencies and proposed integration order

All three PRs below were **open, draft, unmerged and mergeable against their current bases**. GitHub returned an empty review decision for each; independent approval is not established. Each inspected head had five successful hosted checks. Mergeability and passing checks are not approvals. These facts apply to these exact versions, not later changes.

| Work | PR and branch | Exact inspected head | Base and dependency |
|---|---|---|---|
| Completion plan, development container and count UX/recovery | [PR #56](https://github.com/mpeng98-source/Restaurant-AI-central/pull/56), `codex/platform-completion-plan` | `a5330af052dded7851486c087d846aacc8ba99f3` | `main`; independent of the approval/pilot features, but overlaps their count-page changes |
| Independent approval, rejection and reversals | [PR #7](https://github.com/mpeng98-source/Restaurant-AI-central/pull/7), `codex/sprint-2c-approvals` | `efe74a6b29609b2d26d9c3b5df4c73bee0dc361b` | `main`; required before PR #9 |
| Opening stock, private photos and pilot operations | [PR #9](https://github.com/mpeng98-source/Restaurant-AI-central/pull/9), `codex/sprint-2d-pilot-readiness` | `5ec312eff03b8cb95184a69434d9bfc648a3fd47` | `codex/sprint-2c-approvals`; contains the inspected PR #7 head |

Inspected `main`: `d5fb06c24e94305c09f78bd0f719554a6853425f`. Earlier inventory PRs #3 and #5 are already merged; historical runbooks showing them as pending are not the current stack.

**Recommended eventual order:** independently review and explicitly approve PR #56 first, then integrate the new main into PR #7, preserving both sets of count-page behavior and rerunning checks. After separate approval of PR #7, merge it into main; then refresh and retarget PR #9 to main, independently review its remaining diff and rerun the full pilot suite before any separate merge approval. PR #56 is not a functional prerequisite for #7, but integrating it first reduces the risk of losing its count-validation/recovery changes later. The mandatory inventory dependency is **#7 before #9**.

No merge is requested or authorized by this handoff. An engineer must inspect actual conflicts rather than accept entire files from either side. Every changed head needs fresh tests and review. The handoff itself is a subsequent documentation-only update to PR #56; the SHA above is the pre-handoff snapshot with the verified implementation and recorded results.

## 2. Implemented work and evidence

Use the [completion inventory](https://github.com/mpeng98-source/Restaurant-AI-central/blob/a5330af052dded7851486c087d846aacc8ba99f3/docs/platform-completion-plan.md) for the main-platform foundation, capabilities and explicit scope limits. Do not confuse unmerged branch capabilities with functionality shipped on main.

| Version | Implemented scope | What was actually verified and where |
|---|---|---|
| PR #56 snapshot | Field-associated quantity errors, exact-decimal unsaved-entry detection, discard warnings, honest uncertain-save/network/server/conflict/session-expiry messages; reusable non-root development container reading Node/pnpm pins from manifests | [Hosted platform run 41984420657](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41984420657) and [accounting/permit run 41984420720](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41984420720): five checks successful. Implementation head `d39a32945e0eeba6cb0d65317a15294b8fbd61ba` had [run 41982666614](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41982666614) with 47 backend tests and 22 frontend regressions, zero failures/skips, plus [run 41982666580](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41982666580). Local non-root container checks verified Node 24.22.2, pnpm 11.25.0, frozen install, typecheck/lint/build and HTTP smoke; the development-container build is local evidence, not a hosted container-build job. |
| PR #7 snapshot | Human approval/rejection, four-eyes separation, exactly-once immutable adjustments, stale-ledger rejection and append-only reversals; migration 0004 | [Hosted run 41954886534](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41954886534): 73 backend tests and four WebKit scenarios, zero failures/skips; frontend checks/build, PostgreSQL/Redis, Compose, security regressions and secret scans successful. [Accounting/permit run 41954886508](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41954886508) also successful. Counts were checked against hosted logs during handoff preparation. |
| PR #9 snapshot | Independently approved opening stock, protected JPEG/PNG evidence/access/retention, create-only catalog imports, bulk opening proposals, manual reconciliation and authenticated CLI; migration 0005 | [Hosted run 41978774387](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41978774387) and [accounting/permit run 41978774410](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41978774410): five checks successful. Downloaded JUnit/browser reports verified 124 backend tests and six WebKit scenarios, zero failures/errors/skips. Hosted logs verified seven CLI commands, legacy migration/data integrity, synthetic database restore, frontend checks/build, Compose/private-volume/privacy probes and secret scans. |

Run pages contain logs and artifact links. Reports/screenshots have short retention (seven days for the inventory verification artifacts); an independent reviewer should download available non-sensitive evidence and record its digest in the approved review store before expiry. Missing/expired artifacts require rerunning tests, not assuming their contents. Do not archive fixture credentials, traces, server secrets, databases or real photos in the repository.

### Read these existing documents instead of duplicating procedures

- [Architecture](https://github.com/mpeng98-source/Restaurant-AI-central/blob/a5330af052dded7851486c087d846aacc8ba99f3/docs/architecture.md), [security model](https://github.com/mpeng98-source/Restaurant-AI-central/blob/a5330af052dded7851486c087d846aacc8ba99f3/docs/security-model.md) and [operations](https://github.com/mpeng98-source/Restaurant-AI-central/blob/a5330af052dded7851486c087d846aacc8ba99f3/docs/operations.md).
- [Approval implementation/contracts](https://github.com/mpeng98-source/Restaurant-AI-central/blob/efe74a6b29609b2d26d9c3b5df4c73bee0dc361b/docs/sprint-2c-approvals.md).
- [Pilot implementation and historical verification record](https://github.com/mpeng98-source/Restaurant-AI-central/blob/5ec312eff03b8cb95184a69434d9bfc648a3fd47/docs/sprint-2d-pilot-readiness.md).
- [Controlled staging/pilot runbook](https://github.com/mpeng98-source/Restaurant-AI-central/blob/5ec312eff03b8cb95184a69434d9bfc648a3fd47/docs/sprint-2d-pilot-runbook.md): source of the detailed staging, import, recovery, retention and device-test steps.
- [Implementation security self-review](https://github.com/mpeng98-source/Restaurant-AI-central/blob/5ec312eff03b8cb95184a69434d9bfc648a3fd47/docs/sprint-2d-security-review.md): historical findings and fixes, **not independent approval**.
- [Stack integration record](https://github.com/mpeng98-source/Restaurant-AI-central/blob/5ec312eff03b8cb95184a69434d9bfc648a3fd47/docs/issue-18-integration.md).
- [Development environment instructions](https://github.com/mpeng98-source/Restaurant-AI-central/blob/a5330af052dded7851486c087d846aacc8ba99f3/README.md#preinstalled-development-toolchain).

### Known limitations

CI uses synthetic data and WebKit emulation, not a physical iPad, native Safari/camera certification, real restaurant quantities or a live pilot. The synthetic PostgreSQL restore does not verify paired private-photo recovery. The photo adapter is single-host private filesystem storage, not managed multi-host object storage or WORM compliance. Real antivirus success/signature freshness, SMTP delivery and operational monitoring remain unverified. Images aid identification only; employees confirm quantities. Unsaved entries remain in memory, not offline synchronization; browser/device termination can lose them. There is no verified Toast depletion, automatic ordering, autonomous stock adjustment or production release. Passing unrelated Dev Agent checks does not authorize activating that agent or bypassing scope gates.

## 3. Future live-pilot independent security reviewer brief

**Reviewer:** a named human who did not author these changes, with experience in Python/FastAPI, PostgreSQL authorization/RLS, web sessions and private-file storage. Review the exact versions above and their combined integration after any head changes. Repository access is granted only by the owner; begin with least-privilege read access and synthetic test environments, not live restaurant or production credentials.

| Review area | Questions and evidence to require |
|---|---|
| Authentication and sessions | Inspect invite-only onboarding, password hashing, opaque server-side sessions, expiry/revocation, reset/invite replay, cookies/TLS, CSRF and rate limiting. Verify negative cases and that frontend recovery never extends sessions or bypasses authorization. |
| Tenant/location authorization | Trace every count, decision, opening, import, reconciliation and photo request from authenticated assignments to server permission checks. Attempt other-organization/location and other-counter access; never treat client location IDs or UI visibility as authorization. Verify revoked access fails. |
| PostgreSQL RLS and roles | Verify forced RLS, scoped keys/policies and transaction-local context; missing context must fail closed. Test directly with the restricted app role, not superuser/BYPASSRLS. Check connection pooling, trigger/function search paths and raw SQL denial. Keep fixture/migration privileges separate from runtime. |
| Immutable audit and ledger | Verify ordinary users cannot update/delete/truncate audit or posted stock records. Test independent proposer/reviewer separation, duplicate/concurrent decisions, idempotency input mismatches, stale balances, rejection with zero posting, exactly-once opening/adjustments and compensating reversals without history edits. |
| Private photos | Inspect type/magic/decoded-size/metadata stripping, paths and permissions, grants bound to current session/user, same-count ownership, revocation, CSRF, no public routes/logged tokens, retention/hold/tombstones, integrity checks, upload cleanup and uncertain commits. Require real scanner tests separately; sanitizer-only tests are not malware certification. |
| Migrations | Verify historical migrations are unchanged; inspect 0004/0005 invariants and actual fresh/legacy upgrades. Financial history migrations are forward-only; do not use destructive downgrades as a recovery test. Check ownership, grants, numeric finiteness and trigger order. |
| Recovery and operations | Evaluate consistent database/photo backup pairing, crash/orphan reconciliation, restore ownership/RLS/ACLs/tombstones, holds and erasure retries, scoped secret storage, logs/redaction, monitoring and stop/forward-fix procedures. Synthetic CI recovery does not approve actual staging recovery. |

**Required deliverable:** dated report naming the reviewer, exact reviewed SHAs, methods/tests/run IDs, coverage and exclusions, findings with severity and reproduction, remediation owner, and verification of each fix. Explicitly state approval or remaining blockers; changes after review need delta review. Store private evidence in an access-controlled owner-approved location and put only sanitized findings/references in GitHub. Code review approval, operational acceptance and owner merge/pilot authorization are separate decisions.

## 4. Future live-pilot gates and evidence that closes them

Every future-live gate below remains **OPEN / UNVERIFIED** unless it is described as an approval still required. These are not synthetic internal-demo prerequisites; merge/deployment authorization remains necessary for those actions in either scope. The owner may assign roles to suitable people; the engineer/assistant cannot impersonate the owner, counter or independent approver.

| Gate | Who must complete it | Owner input/resource needed | Evidence that closes it |
|---|---|---|---|
| Independent security approval | Independent human security reviewer; engineer fixes findings | Select reviewer, approve scope and least-privilege access | Signed/versioned review report, resolved findings with retest evidence and explicit approval; not the implementation self-review |
| Integration and merge authorization | Owner and assigned repository maintainer | Decide whether to approve each PR separately, following section 1 | Recorded owner authorization, refreshed-head CI and independent reviews for each final diff; no automatic merge |
| Controlled staging provision and access | Staging/operations engineer | Approve an isolated non-production environment, hosting model and any spending; authorize scoped secret delivery | Documented TLS/private networking/encryption, separated database roles, safe secret handling, correct readiness/health and restricted-role tests |
| Real scanner readiness | Operations engineer, reviewed by security reviewer | Approved scanner-equipped runtime and signature source; non-root execution access | Clean scan, approved harmless antivirus-test rejection, timeout/unavailable handling, fresh signatures and tested monitoring; uploads remain disabled until passed |
| Catalog/opening accuracy and restaurant rehearsal | Restaurant manager/owner, assigned employee counter and a different authorized GM/Owner approver | Approved SKUs/zones/categories, vendors/costs where applicable, units/pack factors, signed opening sheet and signed physical count sheet | Human-confirmed preview/import, independent decisions, ledger/manual-sheet reconciliation across required items, rejection/retry/stale-receipt/reversal results and dated human sign-off |
| Physical iPad Safari acceptance | Actual employee and GM/Owner testers with test coordinator | Pilot iPad, Wi-Fi conditions, camera permission and scoped test accounts | Device/iPadOS/Safari versions, portrait/landscape results, keyboard/touch, JPEG/HEIC, network loss/retry/double-tap/refresh, auth expiry/CSRF/logout and location-denial evidence with human sign-off |
| Paired staging backup/recovery | Operations engineer with security reviewer | Encrypted backups/private volume, approved backup credentials, disposable restore target and test authorization | Consistent paired snapshot and checksums; restored ledger/audit/openings/photos/tombstones, correct ownership/RLS/permissions, actual recovery rehearsal and documented outcome |
| Retention, device/privacy policy and operational monitoring | Owner sets policy; operations implements; security reviewer checks | Decide retention/holds/device handling and single-host suitability; name daily retention/operator and alert recipients | Approved policy, hold/release/expiry/erasure and failure retries, orphan handling, tested readiness/quota/scanner/integrity/backup-age alerts and operator checklist |
| Email readiness | Operations engineer and owner-approved test recipient | Approved SMTP provider/sender/test inbox and scoped managed secret; approve any spending | Real invitation/reset delivery and expiry/replay tests without exposed tokens |
| Load/operational acceptance and pilot go/no-go | Owner, restaurant lead, operations and reviewer | Agree realistic pilot user/upload/count load, support ownership and acceptable recovery window | Recorded load/stop/support rehearsal and explicit pilot approval after applicable gates close; this is not production authorization |
| Multi-host/provider expansion or production | Owner and engineering/security leads | Separate approved scope, access/spending and deployment decision if requested | New design/provider isolation/recovery evidence and separate release authorization; not necessary to claim the existing single-host controlled pilot works, and not authorized here |

The engineer can prepare procedures, run synthetic checks, fix findings and record results independently. Actual quantities/approvals must come from humans; devices, stage infrastructure, production email/scanner and backup evidence require the resources above. No additional features should be invented merely to keep coding.

## 5. Future live-pilot checklist for a nontechnical owner

1. **Choose two technical people or roles first:** an independent application-security reviewer and an operations/staging engineer. Ask for experience with PostgreSQL RLS, web authentication and private-file recovery. The reviewer must not be the code's author. Approve their scope/budget yourself; nothing has been purchased or hired.
2. **Send the reviewer this handoff.** Ask for the deliverable in section 3 and a quote/availability. You or your administrator decide access. Start with only the repository access needed; do not send passwords, database URLs or real photos in chat.
3. **Decide the controlled pilot boundaries.** Confirm a small Burbank pilot and whether a single-host private-volume design is acceptable. Decide photo retention (the runbook proposes 30 days, not an approved business policy), holds, permitted viewers/deleters and device handling. Name the daily operator and alert recipient.
4. **Ask the operations engineer for a staging proposal.** Require an isolated non-production host, HTTPS, encrypted backups/private evidence, PostgreSQL/Redis, separated app/migration roles and managed secrets. Approve services/spending and scoped access before provisioning. Require real antivirus and signature monitoring; the default image does not supply that certification.
5. **Assign restaurant participants.** Name the manager responsible for catalog correctness, an employee counter, and a different authorized GM/Owner approver. Prepare approved item/unit/pack lists and signed opening/count sheets in a private document store. Never substitute sample catalog data for the restaurant's approval.
6. **Provide the pilot iPad and schedule testing.** Have employee and manager testers complete the runbook's actual Safari/camera/network-loss cases and record results. Screenshots from CI do not close this item.
7. **Require operational evidence before pilot permission.** Ask operations to demonstrate paired database/photo restore, safe erasure/holds, monitoring/alerts, appropriate load and real email delivery. Keep secrets/backups/private evidence outside GitHub documents and public artifacts.
8. **Review findings and final versions before approving code integration.** Have the engineer fix confirmed issues and rerun CI; have the reviewer verify fixes. If you choose to authorize merges, do so separately in the proposed #56, #7, #9 sequence with refreshed checks. Do not authorize a merge merely because the buttons are green.
9. **Make a separate pilot go/no-go decision.** Review the closed-gate evidence and support/stop plan with the restaurant lead and reviewer. Leave failed or incomplete gates open. A pilot decision does not authorize production deployment, POS integration, automatic ordering or autonomous inventory changes.

## 6. Optional message to a prospective live-pilot reviewer

> We need an independent security review of a multi-tenant restaurant inventory platform before a controlled pilot. The review covers authentication/CSRF, organization/location authorization, PostgreSQL forced RLS and restricted roles, immutable audit/stock records and independent approvals, private photo handling, migrations and paired database/photo recovery. Please review the exact PR versions linked in this handoff, reproduce relevant negative/concurrency tests, and provide a dated report with findings, coverage limits, remediation/retest requirements and an explicit approval decision. CI and the author's self-review are supporting evidence, not independent sign-off. Please send your availability, relevant experience, proposed scope and quote; we have not authorized access, spending, merging or deployment. No live credentials or private restaurant data will be sent in this message.
