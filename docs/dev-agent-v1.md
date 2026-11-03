# Chubby Dev Agent v1 — supervised cloud coding assistant

This experimental automation is designed to assist Codex, not replace a human engineering release manager.

## Operation
- Scheduled review runs every four hours (GitHub schedule may be delayed or skipped) and can be started manually.
- A manual `coding` run lets Codex modify a temporary checkout and produces a patch artifact; it **does not commit or push** changes.
- Every run uploads `dev-agent-report.md`. Manual coding runs also upload a `dev-agent.patch` for review and application by a human/Codex developer.
- The existing Sprint 1B/Sprint 2 CI remains the authority for PostgreSQL, RLS, frontend, Compose and Gitleaks acceptance.
- All runs are bounded by runner timeouts. This is not an always-running daemon, and no persistent memory is assumed.

## Setup required by repository owner
1. Add a scoped OpenAI API key as repository Actions secret `OPENAI_API_KEY` in Settings → Secrets and variables → Actions. Do not paste keys into chat or commit them.
2. Review and pin `openai/codex-action` to a verified commit SHA before enabling unattended use; v1 is used in this proposal for initial review.
3. Review the workflow and merge the PR only after confirming the trust model, Actions permissions and cost limits.
4. Open Actions → Chubby Dev Agent → Run workflow to test `review` first. Check artifacts and billing before trying `coding`.
5. Keep `main` protected, require human review, and keep production credentials outside the runner.

## Security
The workflow uses `contents: read`, no GitHub write token, `persist-credentials: false`, and a restricted Codex workspace permission profile. The runner cannot merge or deploy via this workflow. The API key is available only to the Codex action's protected proxy. Outputs are artifacts, not automatic PRs.

## Limitations / next version
- No autonomous issue selection, continuous 24/7 runner, automatic CI failure remediation or PR opening in v1.
- Manual coding runs check out `main`, so stacked draft Sprint 2 branches must be handled separately until branch selection and permission controls are implemented.
- Automated tests may require network/package setup; no green CI is claimed from this workflow.
- A v2 cloud orchestrator could maintain a queue, use GitHub App scoped credentials, start isolated tasks, open draft PRs and react to CI while preserving owner merge/deploy approval.

## 2026-11-03 failed review — API quota

GitHub Actions run `41723701060` failed after Codex started. The authoritative job log says `ERROR: Quota exceeded. Check your plan and billing details.` The missing report/artifact warning is downstream of that failure. The Node.js 20 upload-artifact deprecation warning is unrelated to the quota failure.

**Do not retry repeatedly** until the OpenAI API project/organization quota is resolved. Check https://platform.openai.com/usage, API billing balance, project hard spend limit, organization hard spend limit and approved organization usage limit for the project behind the `OPENAI_API_KEY` Actions secret. ChatGPT plan subscriptions and API billing are distinct. The error text does not establish which specific limit was reached. Never print or paste the API key into logs, issues or chat.

### Scheduling safety

The workflow now requires repository Actions variable `CHUBBY_DEV_AGENT_ENABLED` to be exactly `true` for scheduled runs. When absent or different, scheduled invocations skip the job and do not invoke Codex. Manual workflow_dispatch runs remain available for controlled tests.

After validating one successful manual review, the owner can enable the schedule by setting `CHUBBY_DEV_AGENT_ENABLED=true` in Settings → Secrets and variables → Actions → Variables. The same setting set to `false` pauses scheduled execution. Alternatively disable the workflow from the GitHub Actions workflow page to stop all invocations until re-enabled.

### Reporting and action runtime

A failed run now uploads a minimal failure-status artifact, not a fabricated review. The review profile is read-only. The Codex action is pinned to the commit resolved from its `v1` annotated tag on 2026-11-03, and upload-artifact is pinned to `v6.0.0` (Node 24). The fix is in a draft PR and must be reviewed and merged before it affects `main`.

### Verification

No post-fix CI run or API-billed manual review is claimed here. Confirm Workflow YAML and permissions in PR checks, then fix the quota and manually run `review` on `main` after merging the safety fix.
