# Issue #18: inventory stack integration

## Sprint 2C reconciliation

Baseline: PR #7 head `537e2d820ee5f5eaeb56d61c7e174586e5c1a3b8`; main `2a3c90237b9f258c360572b710556bbdbb40c82a` after PR #5's squash merge. This is a human-supervised integration, not an autonomous Dev Agent v2 task. No `agent-approved` label, gate bypass, force-push, PR merge, or deployment is authorized or performed.

Native three-way merge against common ancestor `c53d18f7c2a2dc5674ad2f370515ebfd8159488f` reported nine conflicts: inventory count APIs, inventory models, API router registration, PostgreSQL inventory test fixtures, Decimal unit tests, dashboard links, counting screen, styles, and interface smoke tests. The workflow merged automatically.

Resolution preserves the complete Sprint 2C versions of count/review integration, model extensions, approval/reversal APIs, immutable ledger metadata, dashboard, counting interface and PostgreSQL fixture factory. Every existing PostgreSQL test body is unchanged. The additional Decimal case-to-piece regression from main is retained. Workflow composition retains both main's Dev Agent security job and 2C's real PostgreSQL WebKit acceptance and report upload. All main-only Dev Agent files are retained byte-for-byte, including the autonomous change gate and its workflow.

Authorization is identical on both branches. Migrations `0001_foundation`, `0002_inventory`, `0003_inventory_counting`, and `0004_inventory_approvals` are retained byte-for-byte, including forced RLS, four-eyes enforcement, scoped keys, posting locks, exactly-once decisions, audit immutability, stale-ledger detection, and append-only compensating reversals. No replacement migration or schema change is introduced. Restricted application-role testing remains mandatory; zero backend skips are enforced.

The integration commit has the old 2C head and current main as ordered parents. PR #7 targets main. PR #9 remains stacked on `codex/sprint-2c-approvals`; it will only be reconciled after the complete 2C hosted workflow succeeds. Actual CI URLs, test counts and mergeability are recorded in the PR descriptions and the integration report, without claiming future runs have passed.

## Verification and remaining gates

Hosted verification must execute PostgreSQL 16/Redis connectivity, migration-owner upgrades, restricted-role backend/RLS/authentication/concurrency/idempotency/reversal tests, WebKit tablet scenarios and SQL balance assertions, frontend frozen-lockfile/typecheck/lint/build, full Compose health/startup/shutdown, Dev Agent security regressions, and current-tree/all-history Gitleaks. Source identity and local unit checks do not substitute for those runtime checks.

Automated WebKit is not physical iPad Safari UAT. Production SMTP, production deployment and independent human security approval remain unverified. This reconciliation does not authorize merging either PR or moving into production.

## Main advanced during verification

The initial 2C integration `920c72b1c4df7d26f65c224dc4b4bcc769fc21e1` passed [run 41738486777](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41738486777): 73 backend tests, four WebKit scenarios, four Dev Agent gate tests, no failures/skips, and all four jobs green. Before any 2D publication, main advanced to `cedff3e5ed3def63ccfdadb3b0cc53e80b89e2fe` through the separate Dev Agent v2.1 queue work. It adds three queue source/test/document files and two workflow steps for nine queue tests and compilation; it changes no inventory, authorization or migration files.

A second native merge of latest main into 2C is conflict-free. It preserves every 2C inventory/security source and test file, migrations 0001–0004, all main Dev Agent files, and both sets of workflow steps byte-for-byte apart from the documented workflow composition and status documentation. This refresh is another two-parent integration commit, with the already-verified 2C head first and latest main second. The complete hosted suite must pass again, including the nine new queue regressions. The earlier successful run remains historical evidence and is not substituted for the refreshed-head result. PR #9 publication remains gated on that result. No autonomous queue or model run is triggered by this integration.

### Second concurrent main update

The first refresh `bb6336f3f2a6b12a46c25b5bf4024e1666caf43b` passed [run 41739549901](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41739549901): 73 backend tests, four WebKit scenarios and 13 Dev Agent regressions, zero failures/skips, all four jobs green. Main then advanced again to `536635e92d6abd59d9ea6eb74830ac7e04d586a9`, adding the read-only GitHub snapshot collector, five unit tests, a manual read-only dry-run workflow, and two existing CI job steps. No inventory/auth/migration code changed. This second conflict-free main refresh preserves the snapshot and dry-run safeguards as well as all inventory source and migrations. A fresh full hosted run, including all 18 Dev Agent regressions, is required before 2D publication. Earlier successful runs remain explicitly historical.
