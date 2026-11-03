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
