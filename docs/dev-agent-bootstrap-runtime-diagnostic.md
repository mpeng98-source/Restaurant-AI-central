# Bootstrap runtime permission diagnostic

This manual diagnostic measures the actual GitHub Actions job token's ability
to retrieve security metadata. It never creates a Bootstrap claim, calls a model,
produces a coding permit, changes activation variables, or authorizes spending.
It does not establish whether the historical failed run incurred a charge.

The job uses existing Environment `dev-agent-bootstrap-v1`: Required reviewers,
prevent self-review, no administrator bypass, and main-only branch restrictions
must remain saved. No new Environment or credentials are provisioned by this PR.
Only `github.token` is mapped; no Environment or repository Secret is referenced.
The dedicated OpenAI key is never read, passed, or tested.

## Permissions and trusted boundary

The protected job exactly matches Bootstrap: `contents: write`, `actions: read`.
Global permissions are read-only and checkout does not persist credentials.
Actions read permits Environment/deployment branch policy reads. Contents write
is retained solely for a valid comparison with Bootstrap's actual token scope;
it is not a tag-only capability. Reducing it for this comparison could change
metadata visibility and cannot establish what Bootstrap's token sees. No
administrator, workflow-write, signing or attestation permission is added.

The independent script has only a GET interface, an exact endpoint allowlist,
no request bodies, no redirect following, no proxy credentials and no retries.
Pinned checkout/setup actions execute only reviewed main code. A compromised
reviewed workflow could misuse its write-capable token: source review and branch
protection remain the trust boundary, not a claimed platform-enforced GET scope.

## Separately approved operation after merge

1. Keep Bootstrap and normal coding activation variables false. Confirm protected
   Environment settings and an independent eligible reviewer before running.
2. Review the merged full main SHA. Manually select **Bootstrap runtime permission
   diagnostic (GET only)** on `main` and supply that SHA as `approved_sha`.
3. The independent reviewer checks the workflow and SHA before approving the
   existing protected Environment. Re-runs (attempt > 1), branch dispatches and
   mismatched workflow/approved/checkout SHAs deny before the script's API calls.
4. Inspect sanitized per-stage output. `PASS` means that particular check was
   verified. `FAIL` means a known violation or missing resource. `UNKNOWN` means
   unavailable, redacted, malformed or otherwise unverifiable evidence. Either
   FAIL or UNKNOWN produces `overall: DENIED` and exit 2.
5. An all-PASS run is diagnostic evidence for that token and instant only. It is
   not a signed attestation, replayable execution authority or permission to
   dispatch Bootstrap. Main is checked before and after metadata collection,
   but no atomic snapshot with future tag creation exists.

Endpoints are limited to main ref GET, the exact Environment GET, its deployment
branch policies GET, and ruleset **26511987** GET. Ruleset identity, repository
source, exact tag include/no excludes, active enforcement, explicit empty
`bypass_actors`, and update/deletion restrictions must all pass. Missing bypass
metadata is UNKNOWN, never an inferred empty list. Environment protections,
an independently named user reviewer, and exactly one `main` branch policy are
mandatory. GitHub's actual protected deployment gate supplies the approval;
the script does not infer approval solely from a configured reviewer name.

No response body, token, URL, header or raw error is logged. HTTP 403 is UNKNOWN;
404 is FAIL. Timeouts, oversize/invalid JSON and unexpected types deny. A denied
diagnostic does not consume or reset the permanent one-time claim.

GitHub documents that ruleset metadata GET uses Metadata read, but
`bypass_actors` is returned only with write access to the ruleset. This diagnostic
resolves actual runtime visibility without adding administration. If it remains
UNKNOWN, retain the existing denial and evaluate the separately reviewed trusted
preflight proposal in `dev-agent-bootstrap.md`; do not weaken the check.

References: [Environment API](https://docs.github.com/en/rest/deployments/environments#get-an-environment),
[branch policies](https://docs.github.com/en/rest/deployments/branch-policies#list-deployment-branch-policies),
[ruleset visibility](https://docs.github.com/en/rest/repos/rules#get-a-repository-ruleset).

Implementation validation uses offline fake transports. The required accounting
CI runs both Bootstrap and diagnostic regressions without calling live APIs.
Implementation and CI do not dispatch this manual diagnostic or Bootstrap.
