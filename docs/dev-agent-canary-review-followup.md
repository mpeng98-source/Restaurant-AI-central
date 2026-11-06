# Independent-review follow-up

2026-11-06. Addresses review of `4f5ceb0`. The workflow hold, allowed refs,
permissions and live settings remain unchanged. The workflow change remains an
unapplied [patch](../experiments/canary_candidate/workflow.patch). No paid call,
push, merge, deployment or credential modification occurred.

## 1. Candidate HTTPS coverage: resolved offline

[`test_tls_candidate.py`](../experiments/canary_candidate/test_tls_candidate.py)
executes the exact candidate `BROKER` source in a subprocess using real
`http.client.HTTPSConnection`, SSL handshake/SNI and HTTP response parsing. The
fixture changes only socket destination (the fixed API host is asserted, then
mapped to loopback) and trusted certificate root. It does not mock HTTPSConnection
or return a fabricated response object. The local certificate names api.openai.com;
its temporary private key is synthetic and removed after testing. No external
socket can be opened by the fixture mapping.

Seven real-TLS cases cover exact request/payload/project headers, 307/429/503 with
one request and no reconnect, untrusted certificate rejection, oversized/compressed
body rejection, truncated reply, chunked response and a slow body terminated by an
external subprocess watchdog. Chunked success exercises a meaningful difference
from the earlier custom Content-Length-only transport. The slow-body test uses a
one-second test watchdog; the candidate's twenty-second Docker cleanup remains
covered by its orchestration test. Real Docker daemon-loss cancellation is not
claimed.

**All 16 candidate tests passed in the pinned Python image** under UID65534,
network=none, read-only root, dropped capabilities and resource limits. Source is
copied through stdin to disposable tmpfs; there are no repository/secret/Docker
socket mounts. An initial read-only source-mount attempt failed because checkout
directories are mode0700. No permissions were changed; the stdin bundle resolved
that test-access issue. The reusable command is:

```
python experiments/canary_candidate/run_pinned_tests.py
```

This is candidate transport acceptance against a local provider, not OpenAI live
compatibility, account entitlement, pricing validation or live egress containment.

## 2. Evidence retention: implemented in the review patch

The candidate writes `scoped-canary-result.json` atomically at admission, before
dispatch, immediately after receiving a response, and after successful tests.
It preserves run/SHA/project/model bindings, request digest, response digest and
bounded numeric token usage. Usage is retained even when code validation fails.
Failure states distinguish no dispatch from uncertainty. Reservations are never
settled or refunded by this evidence.

Only validated arithmetic source can appear in the record. Raw provider bodies,
headers, exception messages, stderr, credentials, plans and admission receipts
are not uploaded. The numeric usage record currently contains input/output/total
counts; detailed cache pricing is not reconstructed. It is execution evidence,
not sufficient final billing evidence by itself. `provider_calls: 1` means one
attempt was admitted; in timeout/connection failure it does not prove delivery.

The proposed workflow adds the already pinned upload-artifact action with
`if: always()`, the exact evidence-file path, unique run/attempt/SHA name,
`if-no-files-found: error` and seven-day retention. It does not upload RUNNER_TEMP
wholesale. Failed validation with an available response retains sanitized usage;
an absent record produces an explicit artifact-step error. Artifact upload itself
was not run. Hosted artifact access/storage and retention are part of the review,
not a secret-free claim about repository audience. Synthetic source and token
counts are the intended content.

A hard host loss or cancellation can still prevent `always()` from executing.
Pending reservation/authorization remains in the existing control store; absence
of the artifact is uncertainty, never permission to replay or refund. Guaranteed
cross-host evidence delivery would require a durable outbox/remote sink, which is
not implemented by this patch.

## 3. Receipt timing: safe failure fixed; liveness limitation remains

The existing authorization receipt lasts 300 seconds; the preceding signed permit
lasts only 120 seconds. Neither duration was increased or refreshed. A new
`--check-admission` invocation reuses the existing `admit` validator before image
pull. The candidate revalidates after setup and immediately before provider launch,
requiring at least 30 seconds remaining. Context/task binding and the original
300-second interval remain mandatory. Tests cover the exact 30-second boundary,
expired/future receipts and expiration during setup; the latter dispatches zero
provider containers and records `not_dispatched`.

**Manual approvals can still exhaust the receipt.** The separate `authorize` job
mints it before `generate` receives its environment approval. Moving the check
cannot eliminate that wait. Likewise, pre-pulling in a different hosted job does
not guarantee this fresh runner has the image. These checks make refusal early
and explicit, not guaranteed progress. Do not renew a receipt, rerun an uncertain
request or fabricate an authorization timestamp.

Eliminating the liveness gap requires a separately reviewed orchestration change:
perform durable authorization after the final protected approval while preserving
separation of verifier credentials from inference. Simply moving verifier DB/HMAC
secrets into the inference environment would expand access and is **not** proposed
or performed. A trustworthy just-in-time handoff/service needs its own concrete
design and tests before configuration approval. For this one-shot candidate,
reviewers can coordinate prompt approval, with expiry treated as a failed attempt;
that is not a reliable 24/7 design and does not justify disabling reviewers.

## Remaining security decision and release status

The action-time review remains the exact scoped-canary workflow patch: permitting
the synthetic path through the hold, trusted-broker access to the existing key,
Docker bridge egress and now seven-day upload of sanitized execution evidence.
No new general or $5 spending approval is needed. The broader bridge network is
still code-restricted, not a demonstrated host allowlist. Receipt expiry remains
a possible blocker. Persisted environment protections, existing credential binding,
eligible issue and existing control-store admission remain to be verified.

The timing limitation must not be presented as resolved by a longer receipt.
No persistent access expansion is necessary for the delivered fixes; a future
just-in-time authorization design could require one and must be reviewed on its
own. Allowed refs remain main only. Nothing was merged or deployed. The proposal
is reviewable, but no paid run or production readiness is claimed.

Validation: 16 tests passed in the pinned offline image; `git apply --check` and
`git diff --check` passed. Active workflow/scripts/ops have no modifications.
