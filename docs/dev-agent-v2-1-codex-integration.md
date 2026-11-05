# Chubby Dev Agent v2.1 — queue to Codex integration

This change adds a **separate** v2.1 workflow, leaving the already tested v2 workflow unchanged.

## Execution
1. Read all open GitHub Issues and PRs using the paginated read-only snapshot collector.
2. Select only open Issues with **both** `agent-approved` and `agent-safe`, reject blocked/human-only/high-risk issues, and skip an Issue with an existing open Agent proposal PR.
3. Materialize the selected Issue as untrusted task data.
4. Run bounded Codex with the existing workspace restrictions and file-change gate.
5. Only after Codex exits, use the separately scoped PR token to push an isolated branch and create a **draft** PR. CI runs separately on that PR. No automatic merge or deploy.

## Controls
- New workflow: `.github/workflows/chubby-dev-agent-v2-1.yml`.
- Scheduled runs are disabled unless repository variable `CHUBBY_DEV_AGENT_V21_ENABLED=true`.
- Manual `workflow_dispatch` is available only after merge to main; `issue_number=0` selects the oldest eligible Issue. A specific number still must pass every safety gate.
- Requires `OPENAI_API_KEY` and `CHUBBY_DEV_AGENT_PR_TOKEN` secrets for a real coding run.
- No Issue eligible means no Codex invocation, no PR and no model cost.
- All untrusted Issue text remains task data; no issue is permitted to override Codex sandbox, path gate, or human approval.
- GitHub token is not provided to Codex; it is used in deterministic post-Codex steps.
- Existing v2 workflow remains intact. Do not enable both schedules at the same time.

## Acceptance plan
1. CI: snapshot, queue, task preparation, gate, PostgreSQL, frontend, Compose and secret scan all pass.
2. Manual no-eligible-Issue run returns `selected=false`, with no Codex execution.
3. Apply both labels to a small test-only Issue. Manual run with its number creates one draft PR; verify changed paths and CI.
4. Retry the same Issue while its draft PR remains open: it must skip without model execution.
5. Verify an unapproved or high-risk Issue cannot be selected even when manually requested.
6. Review API usage and permissions before enabling the v2.1 schedule. Keep auto-merge and production deploy prohibited.

**No scheduled execution, merge, deployment, or actual end-to-end Codex run is claimed by this PR.**
