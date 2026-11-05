# Dev Agent v2.2 reliability preflight — review required

This is an **offline test-only slice**. The production v2.1 coding workflow is unchanged.

## Verified by new regression tests (subject to hosted CI)
- Closed Issue #24 is ineligible, even when requested manually.
- An existing open Agent proposal PR blocks duplicate selection.
- Failed, pending, skipped, and unknown CI jobs are never interpreted as successful.
- A deterministic budget preflight rejects exhausted daily estimates, maximum run counts, invalid numbers, and missing estimates.

## Important limitations
- Budget preflight is **not a hard API spending cap**. It consumes externally supplied, trustworthy daily spend and run counts, and a conservative estimated maximum per run. It does not retrieve billing data or prevent an individual API call from exceeding an estimate. Enforce real spending controls through the OpenAI API project budget/alerts, credential restrictions, and job timeout.
- CI triage consumes sanitized job metadata only, not raw logs. It does not diagnose root causes, invoke Codex, or automatically retry failed CI.
- GitHub job metadata is supplied as JSON for offline testing; no GitHub API collector is connected to this preflight yet.
- Duplicate detection depends on open PR title matching; it does not prevent races between concurrent workflows or retries after a PR is closed. A durable claim mechanism and concurrency tests are required before scheduling.
- Never include secrets, raw logs, or untrusted PR text in a model prompt.
- No automatic merge, production deployment, or schedule enablement.

## Next acceptance
Review PR and hosted CI. Then build a separate, manual-only GitHub metadata triage workflow with rate-limit and error handling. Implement a persistent per-Issue claim and a verified billing/run-count source before wiring any budget gate into automated Codex execution.
