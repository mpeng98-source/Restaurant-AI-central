# Dev Agent v2.3 — GitHub CI and OpenAI project cost audit

This is a separate **manual, read-only** audit. It does not change the v2.1 Codex coding workflow, automatically retry CI, merge PRs, or enable schedules.

## CI diagnosis
Uses GitHub's paginated workflow-job metadata API (not raw logs) to classify failed, pending, unknown, and successful jobs. Reports counts and a human-review status, not root-cause analysis. Raw logs, step output, and tokens are excluded.

## Credible cost data
Uses the OpenAI **organization Costs API**, grouped by `project_id`, and sums USD costs for the selected project over the last 24 hours. Requires a separately stored organization admin key `OPENAI_ADMIN_KEY` as an **environment secret** in the protected GitHub Actions environment `cost-audit`, not a repository-wide secret. Use a **dedicated API project** for this agent to avoid mixing other application costs. Do not put the admin key in the model prompt or Codex environment.

Cost figures are **settled/reported amounts**, may lag actual activity, and are **not a hard limit** or a guarantee of per-run attribution. A rolling 24-hour window is not the same as a UTC calendar day. If the API response is incomplete or malformed, the collector fails closed. If no rows match the project, the report is zero reported charges, not proof of zero unreported charges.

## Manual test after both stacked PRs are reviewed and merged
1. Create a GitHub Actions environment named `cost-audit` with required reviewers and restrict deployment branches to `main`. Move `OPENAI_ADMIN_KEY` from repository-level Actions Secrets into this environment's Secrets; delete the repository-level copy. Set environment variable `CHUBBY_DEV_AGENT_PROJECT_ID` to the dedicated `proj_...` project ID.
2. Go to Actions → Chubby Dev Agent CI and cost audit (manual) → Run workflow.
3. Enter an existing GitHub Actions run ID. The project ID is read from the protected environment variable, not user-controlled workflow input.
4. Check `ci-summary.json` and `cost-summary.json` artifacts. Compare with the OpenAI dashboard, allowing for reporting delay.
5. Test invalid run ID, malformed response and permission denial; no secrets or raw logs may be printed.
6. Keep the autonomous schedule disabled until a trustworthy usage ledger and enforceable API-side spending limits are in place.

## Security boundary
The collector only fetches metadata and reported costs. No LLM receives either the admin key or raw CI logs. Never use this workflow to grant model write privileges, disable branch protection, or deploy production.

**Do not run the workflow until the environment protection and secret migration are complete.** The organization admin key must not be exposed to unrelated PR workflows. GitHub environment required reviewers are a repository setting and are not configured by this PR.
