# Sprint 2D security review record

Scope: issue #8; baseline PR #7 `00b8f33bfdf354aab6838495ae5d0f162aa7d9ec`, migrations 0001–0005, server authorization/CSRF, inventory HTML inputs, private storage and CI permissions. This is an **implementation self-review**, not the independent review required for pilot sign-off. No independent human or separate security reviewer has signed off. The final draft PR must remain blocked for pilot release until that review occurs.

## Findings and remediation

| Finding | Risk | Change | Verification required |
|---|---|---|---|
| Raw opening movement had no independent approval contract | Unreviewed baseline initialization | Forced-RLS immutable opening proposals/decisions; two people for every quantity; nested posting guard; ledger locks and duplicate protection | Real PostgreSQL approval/concurrency/forgery tests |
| Photo key prefix did not prove protected object ownership | Forged references and no access/retention controls | Scoped metadata, same-session reference trigger, private no-follow/exclusive filesystem objects, current-session-bound grants and integrity checks | PostgreSQL + real API + WebKit upload/view tests |
| Original catalog RLS accepted tenant context without a catalog permission predicate | Employee-context catalog mutation via app connection | Restrictive catalog write policies; restrictive ledger writer policy | Direct restricted-role employee writes/reads and existing RLS regression |
| PostgreSQL numeric NaN satisfies ordinary positive/nonzero checks | Non-finite ledger or unit values could corrupt balances via raw app SQL | Add finite constraints to inventory quantities, factors, thresholds, costs and balances, without modifying historical migrations | Direct real-PostgreSQL NaN rejection tests |
| Session temporary objects could shadow unqualified guard tables | Guard lookups could read attacker-created TEMP relations if SQL access were compromised | Pin inventory function search paths to trusted pg_catalog/public, with pg_temp last; retain invoker rights | Actual PostgreSQL TEMP-table spoofing regression |
| Untrusted images and embedded metadata | Content attacks, EXIF/GPS exposure and resource exhaustion | JPEG/PNG-only magic/format/decode/pixel/size checks, re-encode fresh RGB, bounded chunked/JSON bodies, real Redis rate and persistent location quota | Corrupt/type/size/CSRF/forgery tests; real scanner success remains pending |
| Object deletion cannot atomically share a PostgreSQL transaction | Orphan bytes or stale grants | Commit access-revoking tombstone first, then erase; fail visibly and support retry; no metadata resurrection | Expiration/hold/tombstone/byte erasure tests; storage-failure runbook |
| Default backend image ran as root | Unnecessary filesystem privileges | API/worker/migrator use UID/GID 10001; private volume mode 0700 | Compose runtime checks |

## Preserved controls inspected

- No changes to the four historical migration files. Added policies are restrictive, not a replacement of tenant/location predicates. New tables force RLS; no SECURITY DEFINER functions, elevated app role or public file route. `chubby_app` remains separate from `chubby_migrator`.
- Report locks precede location locks for counts/decisions; movement/opening posting takes the same location advisory lock. Exactly-once decisions and reversals retain unique keys and transaction-wide atomic posting. Historical counters remain in four-eyes detection; rejected reports post nothing. Late ledger activity blocks approval, including net-zero activity.
- Ledger, opening records, operation records and audit records are immutable, including trigger protection for fixture administrator mutations. Evidence identity remains immutable; lifecycle changes require approval permission, reasons and audits.
- Server endpoints derive scope from current authenticated assignments and enforce CSRF for mutations. Photo grants are short-lived, bound to current session and passed in a header. Credentials, original photos and grants are excluded from logs/artifacts. CORS only allows configured origins; production/staging cookie/TLS settings remain mandatory.
- React text rendering escapes untrusted item names/reasons/notes; no `dangerouslySetInnerHTML` or HTML photo formats are used. SKU/code constraints prevent spreadsheet formula prefixes; JSON outputs avoid exporting formula-bearing CSV cells. API fields are bounded, unknown operational fields rejected, and Decimal input rejects binary floats.
- GitHub workflow remains `contents: read`; all third-party actions use previously reviewed commit SHAs. Gitleaks scans current tree and full reachable history, without allowlisting new secrets. Artifacts whitelist JUnit, browser summaries and synthetic screenshots; fixtures, cookies, passwords, database dumps, private photos and server logs are excluded. Retention is seven days. No deployment credentials or deployment job are added.

## Remaining review and pilot gates

1. Named independent reviewer: inspect migration/trigger execution order, RLS permutations, raw SQL denial and all test evidence; record severity/owner/fix/retention requirements. Self-review is not independent approval.
2. Private filesystem adapter is a single-host pilot component. No managed object-store adapter or multi-host guarantees. Review encrypted volume permissions, backup pairing, crash-orphan reconciliation, quota/retention operations and trusted host administrator access. A host or migration administrator can replace code/disable triggers; immutable application history is not a WORM compliance claim.
3. Real antivirus success, fresh signatures, infected-file rejection and scanner monitoring are unverified. Sanitizer-only CI does not prove malware freedom; uploads are blocked outside dev/test without a scanner path. The default image intentionally supplies no antivirus certification.
4. No physical iPad Safari/camera/HEIC certification, real staging deployment, approved operational catalog, signed manual sheet reconciliation, external SMTP delivery or paired staging PostgreSQL/evidence-volume restore has executed in this implementation session. The isolated CI restore, when successful, covers PostgreSQL synthetic data only.
5. Load/penetration testing, managed-device photo handling, multi-instance storage, scheduled retention erasure, provider-specific IAM and disaster recovery remain operational review work. No unauthorized stock mutation or automatic photo quantity inference is accepted.

Record actual hosted outcomes in `sprint-2d-pilot-readiness.md`. Do not label unresolved gates as passed or recommend a live pilot solely from green CI.
