# Chubby Dev Agent v2 — autonomous draft PR prototype

**Status:** Experimental draft PR. Not enabled or deployed.

## What it does
A scheduled or manually triggered GitHub Actions job chooses one open GitHub Issue explicitly labeled `agent-approved`, checks out `main`, invokes a bounded Codex coding session, checks the changed paths, pushes a unique isolated branch, and opens a **draft** PR for human review. Existing CI runs on the draft PR. No merge or deployment is performed.

## Controls
- Scheduled runs are **off by default** unless repository Actions variable `CHUBBY_DEV_AGENT_V2_ENABLED=true`.
- One task per run, every four hours at most; GitHub schedule is best-effort, not guaranteed 24/7 availability.
- Only Issues labeled `agent-approved` are eligible. `agent-blocked` prevents execution. No label = no autonomous work.
- Repeated scheduled runs skip issues with an existing open `Agent proposal: issue #N` PR.
- Job time limit 40 minutes; one bounded Codex call; no retry loop.
- Codex is not given `GH_TOKEN` in its step and checkout does not persist credentials. Only later deterministic GitHub CLI steps receive a scoped token.
- The change gate allows only inventory-related source, tests, and Sprint 2 docs. It rejects workflow, migration, authentication, security and infrastructure edits, as well as symlinks and renames.
- The agent cannot merge or deploy through this workflow. Main branch protections and independent CI/reviews must still be enforced.
- Untrusted GitHub Issue content is task data, not instructions to override safety.
- Production credentials and databases must never be available to the runner.

## Owner setup
1. Review the code, permissions, action pins and GitHub Actions security policy in the draft PR.
2. Configure `OPENAI_API_KEY` Actions secret, with API project billing/usage limits and alerts. ChatGPT subscription is separate from API billing.
3. Confirm Actions setting **Workflow permissions** allows the job's scoped `contents: write` and `pull-requests: write`; repository policy may disallow GitHub Actions creating PRs. Allow only after reviewing security implications.
4. Create the GitHub label `agent-approved`. Apply it **only** to a small, safe Issue suitable for changes to inventory source/tests/docs on current main. Do not label Issues that depend on unmerged Sprint 2B/2C/2D code.
5. Merge the workflow PR only after independent review. Scheduled job will remain skipped unless `CHUBBY_DEV_AGENT_V2_ENABLED=true`.
6. Test manually from Actions → Chubby Dev Agent v2 → Run workflow with an approved Issue number. Confirm a draft PR is opened, CI runs, and no restricted files are changed.
7. If manual tests pass, set `CHUBBY_DEV_AGENT_V2_ENABLED=true` under Settings → Secrets and variables → Actions → Variables. To pause, set it to `false` or disable the workflow.

## Caveats
- No automatic CI failure repair loop, no issue-closing, no daily email report, no multi-agent coordination.
- The workflow may not open PRs if GitHub Actions write permissions or repository policy prohibit it; this is not a reason to weaken branch protections.
- The agent currently starts from `main`, not stacked draft PRs.
- Scheduled selection is conservative; one issue per run, oldest approved first. If no safe approved issue exists, it does nothing.
- The job cannot prove 24/7 uptime. A durable queue/worker with monitoring would be required for service-level guarantees.
- Do not treat the patch as safe without reviewing code and tests.
- Cost controls should be enforced in API project billing; the workflow timeout limits runtime, not guaranteed token spending.

## Acceptance
- No issue labeled: job completes without Codex invocation.
- Unapproved issue number: fail closed.
- Approved safe issue: Codex generates a bounded change, path gate passes, a draft PR is created, CI runs.
- Attempted workflow/migration/auth/security changes: gate fails without push.
- No auto merge, no production deployment.
- Verify GitHub run URLs, artifacts and API usage before enabling schedule.
