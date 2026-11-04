# One-time project billing bootstrap

The Chubby-Dev-Agent project had no usage or Costs rows. The normal coding gate
correctly rejects missing current-day costs. This separate, default-off path
allows **one fixed, tiny text request** to seed billing activity, after explicit
human approval. It cannot accept an Issue, generate code, publish a PR, create
signed cost evidence, reserve a normal coding run, merge, deploy or enable coding.
The normal gate and its unknown-cost denial are unchanged.

## Exact allowance and request

- Repository: `mpeng98-source/Restaurant-AI-central` only.
- Project: `proj_Nkd1G85QX72VHwdQ8mEg8CRa` only; verify the protected API key belongs
  to this project before configuration. An explicit `OpenAI-Project` header binds
  the request. The bootstrap does not prove the identity of other workflow keys.
- Fixed model: `gpt-6-luna`, input `Reply OK.`, at most 16 output
  tokens (reasoning disabled), standard/default tier, no tools, no stored response, no retries.
- Owner review allowance: **USD 0.01 estimated model-token spend**. The reviewed
  standard rates are USD 0.10/M input and USD 0.50/M output. A conservative 1,024
  input-token allowance and 16 output tokens estimate USD 0.0001104. Cache writes at USD 0.125/M would bring that estimate to USD 0.000136. The actual
  prompt is much smaller. The documented model name has no dated snapshot;
  the short review window bounds pricing assumptions, not provider alias changes. This allowance is not a provider hard dollar cap and
  does not limit other users or keys in the project. No hosted tools are used.
- Pricing/model review expires November 7, 2026 at 00:00 UTC; the script denies
  after that date. Extending it requires a reviewed code change, not a dispatch
  input. Confirm current pricing and availability before the live approval.

Sources: [model/pricing](https://developers.openai.com/api/docs/models/gpt-6-luna),
[per-run spending limitations](https://developers.openai.com/cookbook/articles/per_run_spending_controller_responses_api).

## One-use boundary

After validating the manual main context, environment protection and current
main SHA, the trusted script creates an annotated tag object with run, attempt,
SHA, project, request digest and allowance. It then atomically **creates**
`refs/tags/chubby-dev-agent-bootstrap-v1`. GitHub rejects a concurrent/existing
ref. Only a successful creation permits the sole Responses request. The script
never deletes or updates the ref and rejects every `run_attempt != 1`.

The opportunity is repository-wide, not daily and not reset by a new run, project
variable, UTC rollover or cancellation. HTTP errors, timeout, process death,
cancellation or rejected responses burn it. A timeout is an unknown billing
outcome, not permission to retry. Failure before ref creation makes no model
request. Failed duplicate claims may leave unreachable annotated tag objects;
these do not authorize execution.

The GitHub token has repository contents write permission only within the
protected job so trusted code can create the tag. It is not handed to an agent;
the returned model text is never logged, interpreted or executed. The workflow
has no database, Admin Key, signing, publication or Codex credentials.

Administrators and trusted code with repository write access remain privileged:
manually deleting/moving this permanent tag defeats the ledger. Restrict tag
updates/deletions with a repository ruleset for
`chubby-dev-agent-bootstrap-v1`, keep creation available to this workflow, and
restrict workflow modifications. Runtime admission now verifies an active,
no-bypass tag ruleset with both update and deletion restrictions for the exact
claim ref; missing/unreadable protection denies the probe before the claim. Never delete the tag as cleanup or rename it
to retry. This is an at-most-one request admission mechanism, not a guarantee
that the provider processes a request exactly once or that billing appears.

## Configuration and live approval (not performed by this PR)

1. Independently review and merge this change. Leave
   `CHUBBY_DEV_AGENT_GATED_ENABLED=false`; leave bootstrap unset/false until ready.
2. Create environment `dev-agent-bootstrap-v1` with required reviewers, **prevent
   self-review**, **no administrator bypass**, and a custom deployment policy
   allowing only branch `main` (not a tag or wildcard). Runtime API checks fail
   closed if these settings are absent or unreadable. Ensure an independent
   eligible reviewer is available; do not weaken the gate for a single-person
   account. If the GitHub plan cannot enforce these settings, do not activate.
3. Store a dedicated, least-privilege Chubby project `CHUBBY_BOOTSTRAP_OPENAI_API_KEY` in this
   environment. Do not copy an Admin Key. Confirm it can invoke only the required
   model/endpoint where project controls support that restriction. Keep it out of
   repository-level secrets. Protect the permanent tag as described above.
4. Verify `CHUBBY_DEV_AGENT_PROJECT_ID` matches the fixed project and no permanent
   bootstrap ref exists. Set the separate
   `CHUBBY_DEV_AGENT_BOOTSTRAP_ENABLED=true` only for this approved operation.
5. Manually dispatch `Dev Agent one-time billing bootstrap (manual approval)` on
   main with the reviewed full SHA and exact confirmation
   `ONE PROBE; USD 0.01 ESTIMATE; NO RETRY`. The independent environment reviewer
   checks the run SHA, project, estimate, one-use semantics and pricing before
   approving. The script rechecks that main still matches after the wait.
6. After the run, keep the tag permanently, return the bootstrap variable to
   false and keep coding false. Even if the run fails, never rerun a consumed
   claim. Inspect the permanent tag and provider dashboard to reconcile it.
7. Wait for actual project billing rows, then run the existing read-only cost
   diagnostic. Billing may be delayed, extremely small charges may not appear
   immediately, and the UTC date may roll over. A successful probe does not
   establish known spend and cannot authorize the coding workflow. A later coding
   attempt still requires separately approved current UTC-day authenticated costs
   and the normal reservation/permit chain. Never substitute this usage output,
   historical costs, Default project costs, or a synthetic zero report.

No live paid request, permission change, environment setup or activation is part
of the implementation validation. Offline tests simulate the GitHub create-ref
contract and provider; they do not establish live GitHub protection or billing.
