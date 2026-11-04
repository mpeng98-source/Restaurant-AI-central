# Trusted Owner Preflight — design for independent security review

Status: **DESIGN ONLY; implementation and paid Bootstrap NO-GO**.
This document adds no CLI, workflow, SQL migration, credential, public key,
permission, activation, attestation fallback or paid execution path. Merging a
design is not approval to implement, configure or execute it.

## Context and decision

Reviewed baseline: `e18c358d230bed567515a54a72962320042c7fcf`.
The owner reports diagnostic run `41910577970` returned
`ruleset: UNKNOWN`, `ruleset_reason: BYPASS_FIELD_ABSENT`, and overall DENIED.
This identifies an absent field, consistent with documented visibility limits;
it does not prove why GitHub omitted it or establish historical billing outcomes.
Do not repeat the unchanged diagnostic or treat absent bypass data as empty.

This design expands the [existing proposal](dev-agent-bootstrap.md#proposed-separate-trusted-preflight-not-implemented-or-activation-approval).
Recommend a manually operated owner CLI plus the existing Neon control-plane
database, with a new isolated ledger namespace and verifier role. No daemon,
new backend service, or administrator-capable Actions token is necessary.
Recommendation is conditional: deployed database identity, privileges, durability
and operational restore controls have not been audited by this design review.

The CLI uses an **existing** owner identity authorized to retrieve complete
ruleset metadata through GitHub REST. No new owner authority is granted. If that
identity cannot retrieve an explicitly present bypass list, issuance stops.
Only the owner workstation holds the owner GitHub credential and signing key.
No owner credential or private signing key may enter any GitHub Secret,
workflow input, artifact, log, environment variable, repository or runner.

## Security invariants

1. No authenticated complete policy evidence means no admission. Evidence is
   not approval, a coding permit, a spending reservation, or proof of key scope.
2. Independent protected Environment approval remains mandatory. Owner signature
   alone cannot approve the owner's workflow run or bypass self-review controls.
3. Repository, workflow, main SHA, run, attempt, payload, policy, signer, ledger
   authority and freshness must match the verifier's independently pinned context.
4. One attestation consumption per nonce and per repository/purpose/run, including
   concurrent requests; no reset, replacement or release after consumption.
5. No paid request before confirmed permanent atomic GitHub tag-ref creation.
   Only the tag is the repository-wide, cross-run at-most-one paid-call barrier.
6. Preserve the fixed probe, expiry, no retries, no reruns and normal coding hold.
   A preflight success cannot enable any activation variable or coding execution.

## Minimal architecture and trust boundaries

| Component | Authority and allowed actions | Excluded authority |
| --- | --- | --- |
| Owner CLI/workstation | Existing owner credential; fixed-host GitHub GETs; local signature; insert-only ledger registration function | No tag writes, OpenAI credential, provider requests or workflow dispatch |
| Owner signing key | Dedicated Ed25519 key in OS-protected storage; explicit local confirmation per issuance | Never exported to Actions or used for normal coding permits/cost observations |
| Protected verifier job, proposed | Verify evidence; use restricted ledger functions; consume once; emit bounded envelope/digest | No owner credential, signing key, OpenAI key, Contents write or database administration |
| Existing protected Bootstrap job | Existing minimal GitHub scopes; approved fixed probe key; verify bound evidence; create permanent claim; one probe | No owner credential, signing key or database credential |
| Neon ledger | Durable authoritative registration and atomic consumption state | Cannot sign evidence, approve a run or authorize a paid call by itself |
| Independent reviewer | Approve exact reviewed run through GitHub Environment protections | Cannot substitute a review comment for protected deployment approval |

Trust GitHub's TLS API, protected-main execution/approval records, the reviewed
verifier and pinned actions/dependencies, owner workstation/signer, independent
reviewer and ledger authority. A compromised trusted administrator/signer can
invalidate these assumptions; do not describe this as protection against them.
An attacker may control inputs, transport/storage of evidence, workflow comments,
unprivileged branches and an ordinary leaked restricted ledger credential.
Treat all evidence bytes as hostile until strict parsing and signature checks.

### Proposed sequence — not an execution instruction

1. After separate implementation review, a separately owner-authorized new run
   would target reviewed main and attempt 1. No automatic dispatch or rerun.
2. A proposed `verify_owner_preflight` job waits in a separate protected preflight
   Environment. Future owner configuration must require independent reviewers,
   prevent self-review, disable administrator bypass and allow only main.
   Use Contents read/Actions read only, plus an isolated restricted database
   credential; no `id-token: write` or additional GitHub scope is proposed.
3. While the run is awaiting approval, the owner CLI independently retrieves its
   repository, run/attempt, dispatcher, workflow path/ref/SHA and main SHA from
   GitHub. It reads Environment protections, exact branch policy, branch
   protection, the exact tag's absence, ruleset list/details and full bypass data.
   Resolve IDs and source commit from GitHub, not caller-supplied JSON.
4. CLI validates a locally pinned policy, displays a sanitized confirmation of
   run/SHA/nonce/expiry/purpose, signs evidence and registers it immutably in Neon.
   The CLI does not assert that pending Environment approval already occurred.
5. Independent reviewer approves the preflight job within the evidence's short
   lifetime. The verifier authenticates the envelope, checks live readable
   context/policy and ledger identity, then atomically consumes and commits it.
   No waiting/polling, renewal or automatic recovery loop is proposed: missing
   or expired evidence denies the run.
6. Only verifier success with exact run/SHA/envelope digest can unblock the
   existing Bootstrap job. Its existing protected Environment approval is still
   required, even if this means a second approval. Do not remove or weaken it.
7. Immediately before any claim, Bootstrap independently re-verifies the signed
   envelope, context, expiry and main SHA. GitHub's trusted same-run dependency
   must prove the isolated verifier committed that exact digest. Never accept a
   caller-supplied boolean, artifact, receipt or `needs` substitute as admission.
8. Preserve annotated tag-object creation then atomic permanent create-ref;
   confirm the returned exact ref/object before the sole paid request. A signature
   or consumed nonce alone never reaches the model endpoint. No cleanup deletes
   or moves the tag. No OpenAI credential enters the verifier job.

The short lifetime includes both approval waits. Delayed approval causing denial
is intentional. A new run or replacement evidence must not be automatic recovery.

## GitHub collection and policy provenance

Use fixed GitHub API host, repository and GET endpoint allowlists, TLS validation,
bounded response sizes/timeouts, a pinned API version and no redirects or retries.
Do not use a mutable Git remote, shell command interpolation, user-chosen URLs,
arbitrary files or repository-provided scripts to obtain owner credentials.
Retrieve owner credentials through OS-protected storage/normal authorized local
credential provider, never argv, logs or shell history. Do not copy raw API errors.

Require ruleset ID `26511987`, repository numeric ID/name and repository source,
active enforcement, tag target, include exactly
`refs/tags/chubby-dev-agent-bootstrap-v1`, no excludes, explicit `bypass_actors: []`,
and update/deletion restrictions. Do not sign a merely public/redacted response.
Inspect all applicable listed/inherited rulesets; pagination, unknown applicable
rule semantics, unreadable parents or conflicting protections deny issuance.
Bind the exact normalized applicable policy set, not only its friendly name.

Environment evidence includes exact ID/name, Required reviewers and stable IDs,
prevent-self-review, no admin bypass and one main-only branch policy. Verify the
independent designated reviewer has accepted repository access. Branch protection
evidence includes the five required checks and source app IDs, review/latest-push
requirements, no bypass/force-push/deletion. Missing required metadata denies.
Owner credentials used for these GETs may already be privileged; this design
does not grant or transfer that privilege to Actions.

Current direct checks must remain fail-closed until a separately reviewed new
evidence-source implementation exists. It must preserve the same semantic policy
requirements: no silent `UNKNOWN -> PASS` or `missing -> []` conversion. The only
proposed supplemental field is the runtime-redacted bypass list, authenticated
from the signed owner snapshot. Directly visible values must match it; nonempty
bypass, changed policy, unreadable metadata, or another missing required field
still denies. No generic catch-all attestation fallback. Diagnostic behavior
remains unchanged and cannot authorize Bootstrap.

## Canonical signed evidence contract

Envelope transport: bounded JSON containing only `payload` and `signature`.
Maximum envelope 32 KiB; strict schema/version, no unknown or duplicate members,
invalid Unicode, floats, NaN, Infinity, alternate encodings or trailing data.
Use RFC 8785 JSON Canonicalization Scheme (JCS) with a pinned reviewed library,
not an approximate `sort_keys` serializer. Restrict security identifiers to their
canonical ASCII forms. Decimal GitHub IDs are positive canonical strings (avoid
JSON numeric precision loss); timestamps are bounded integer UTC seconds.

Sign `CHUBBY_BOOTSTRAP_OWNER_PREFLIGHT_V1` plus a NUL separator plus canonical
payload bytes using Ed25519 (RFC 8032). Signature is unpadded base64url encoding
of exactly 64 bytes. Algorithm is fixed, not selected by envelope input.
The payload includes the following mandatory bindings:

| Field group | Required contents |
| --- | --- |
| Identity | Schema version, fixed purpose `bootstrap-owner-preflight`, key ID, owner GitHub user ID, repository numeric ID and exact owner/name |
| Execution | Exact workflow path/ref, workflow SHA, run head SHA, approved main SHA, run ID, attempt 1, dispatcher ID, Environment IDs |
| Reviewed code | SHA-256 digests of workflow, Bootstrap script, verifier, canonical policy and public-key manifest from that reviewed commit |
| Policy evidence | Complete validated normalized ruleset/applicable-set, bypass list, Environment, deployment branch and main-protection snapshots; per-snapshot digests |
| Fixed probe | Project/model, canonical fixed request digest, exact permanent ref and reviewed allowance string; never a credential or model response |
| Ledger | Pinned ledger-authority identifier and reviewed epoch; not a caller-selected endpoint or database URL |
| Freshness | Collection start/end, issued-at, expires-at, cryptographically random 32-byte nonce |

Canonical digests cover exact validated canonical payloads, not raw response
formatting or mutable links. Store only the allowlisted security projection;
omit avatars, emails, access tokens, headers and raw provider data. The owner must
validate complete raw responses before projection; never project away unknown
security-critical properties to conceal a policy conflict.

Public verification keys/key IDs are pinned in protected source, never downloaded
from the envelope. Rotation/revocation requires independent reviewed changes and
invalidates old outstanding evidence; no runtime key import. The signature is
verified before any ledger mutation, and again in Bootstrap before claim.

Require collection span <= 30 seconds and `issued_at == collection_end`.
Require `0 < expires_at - issued_at <= 300` seconds, no future issuance beyond
an explicitly bounded clock skew (proposed 5 seconds), and strictly unexpired
evidence using both verifier and database clocks. Clock disagreement/untrusted
time denies. No expiry extension through inputs. Effective expiry is the minimum
of envelope expiry, model/pricing review expiry and run deadline. This design
does not extend the existing model/pricing approval or prove key/model entitlement.

## Neon feasibility and atomic ledger design

Source review found reusable patterns in
[`0001_dev_agent_accounting.sql`](../ops/migrations/0001_dev_agent_accounting.sql):
unique nonce/run constraints, transaction locks, database-clock expiry checks,
SECURITY DEFINER functions with fixed search paths and PUBLIC revocation.
[`dev_agent_rollout.py`](../scripts/dev_agent_rollout.py) additionally audits
function bodies/ACLs and parent role membership. These are architectural patterns,
not proof of current deployed Neon state; no Neon connection was made here.

Do **not** reuse the coding `permit` table or `consume_permit` function: they have
reservation foreign keys and update coding accounting state. Do not fabricate
known costs, enable a coding project or consume a normal coding allowance.
Use a separate schema/table and dedicated functions/roles in the existing
control-plane database, after disposable Postgres/schema-only Neon acceptance.

Proposed immutable registration record: authority/epoch, repository ID, purpose,
nonce, run ID, attempt, SHA, envelope bytes/digest, signer ID and timestamps.
Separate immutable consumption record contains the registration key/digest and
a database-clock consumption timestamp in the committed transaction. Unique constraints must cover nonce and
`(repository_id, purpose, run_id)` across attempts and signing keys. Register only
once; no upsert/replacement, nonce recycle, automatic unconsume or DELETE API.
Tombstones outlive key rotation and pricing windows; epoch change is not reset.

Proposed atomic consume operation takes exact nonce/run/attempt/SHA/digest/epoch
bindings, locks the registered row, uses database clock, rejects any consumed,
expired, mismatched, malformed or unknown registration, and inserts a unique
consumption record in one transaction. Return success only after confirmed
commit. A lost commit response is denial/unknown, never a read-back authorization
or automatic consume retry. Parallel requests yield at most one success.
The database cannot authenticate a signature by trusting a caller's `verified`
flag: reviewed verifier code verifies the pinned signature first, while the SQL
function enforces immutable registered bindings and uniqueness independently.

| Proposed role | Grants | Prohibited |
| --- | --- | --- |
| Non-login schema owner | Own private tables and fixed functions | Runtime login or membership from service roles |
| Owner-workstation issuer login | EXECUTE exact registration function only | Consumption, raw DML/DDL, resets, coding-accounting functions |
| Isolated verifier login | EXECUTE bounded fetch-for-exact-run and consume functions only | Registration, raw table reads/writes, role changes or owner membership |
| Bootstrap paid job | No database credential | Reading, issuing or resetting ledger state |

Every login is NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS;
deny all parent memberships as NOINHERIT does not prevent SET ROLE. Revoke PUBLIC
schema/table/function access and default grants. SECURITY DEFINER functions have
fixed `pg_catalog, pg_temp` search path, fully qualified private relations, no
dynamic SQL, narrow ownership and exact EXECUTE ACLs. Bound fetch sizes; require
TLS and pinned database/branch identity outside the envelope. Re-audit function
fingerprints, ownership, ACLs and role settings before use. A stolen verifier
credential can cause denial of service by consuming evidence, but cannot sign
it, approve GitHub or bypass the permanent claim.

Use only the designated writable authority branch, never a read replica or
developer clone. Neon branching/restore can fork or roll back consumption state;
the ledger is not globally unique across clones. Endpoint secrets, authority
identity and epoch are independently configured and never supplied by the CLI
envelope. Restore/reset/failover identity uncertainty is an incident: freeze
activation, reconcile against GitHub claims and independent issuance/audit
records, and require reviewed recovery. Do not automatically trust a restored
ledger, reset a nonce or delete a tag. Permanent tag enforcement remains the
cross-ledger backstop under the trusted GitHub administration assumption.

## Threat model

| Threat | Required defense / remaining limit |
| --- | --- |
| Forged/altered evidence or substituted public key | Strict canonical parsing, domain separation, pinned Ed25519 key and schema, verify before use |
| Replay to another run/repo/attempt/payload/commit | All context bindings, attempt-1 gate, immutable registrations and atomic nonce/run uniqueness |
| Concurrent consumers or duplicate signing | Database constraints/locking, one registration per run, permanent atomic create-ref |
| Caller tricks owner into signing claims | Owner independently reads GitHub context/policy and confirms issuance locally |
| Malicious artifact/storage or leaked verifier credential | Signature verification, separate issuer/consumer roles, no generic receipt-as-authority; availability attacks remain possible |
| Workflow/branch substitution or stale main | Protected-main review, pinned code/key digests, exact workflow SHA and main checks before claim |
| Approval bypass or colluding owner | Separate eligible reviewer, protected environments, no admin bypass; compromised/colluding trusted parties remain out of model |
| Leaked owner credential/signing key | Keep outside Actions; local secure storage; incident freeze/revoke; signatures cannot defend against signer compromise |
| Database owner compromise, branch clone or restore | Restricted roles, fixed authority, retained audit records and incident freeze; DB admin remains trusted |
| Policy changes after owner collection | Direct visible-policy comparison, short expiry and final main check; residual TOCTOU explicitly remains |
| Crash or uncertain billing/claim response | Never release consumed nonce/tag, never retry paid call; reconcile without execution |
| Sensitive output | Fixed sanitized result codes; no raw API bodies/errors, credentials, envelope dumps or private-key output |

## Failure and recovery policy

| Failure point | Mandatory outcome |
| --- | --- |
| Collection, signature, approval, context or schema failure | Deny; no claim or model call; no fallback or automatic new run |
| Registration acknowledgement lost | Stop; inspect record read-only; do not overwrite/reissue the run |
| Missing/expired evidence or unavailable Neon | Deny; no model call; fail closed on clock/identity uncertainty |
| Consume commit outcome uncertain | Stop; no tag/model call; no read-back-to-allow or retry |
| Consumption committed but claim not created | Evidence remains burned; no automatic fresh nonce or run |
| Tag object exists but permanent ref creation fails/is uncertain | No model call; retain consumed evidence; no update/delete/cleanup writes |
| Permanent claim confirmed, then timeout/cancellation/response rejection | Claim remains permanently consumed; no paid retry even if usage is missing |
| Policy/main changes or expiry during approvals | Deny; do not refresh evidence automatically |
| Signer/owner/ledger compromise or restore | Freeze, reconcile, independent review; never erase permanent claim to recover |

Any proposed later attempt after a pre-claim failure needs fresh owner and
independent approval plus evidence that the permanent opportunity was not used.
Tag absence alone is not proof of no paid request. Reconciliation must consider
authenticated run/provenance evidence and actual provider records; missing costs
are not zero. No diagnostic or failed workflow rerun is authorized by this design.

## TOCTOU: explicit unresolved risk

Owner API reads, independent approval, Neon commit and GitHub ref creation are
separate transactions. Main checks and a five-minute envelope do not lock GitHub
rulesets, bypass lists, reviewer access or branch protection. An administrator
could change hidden bypass metadata after signature but before the claim; the
Actions token cannot independently detect that hidden-field change. Nor can a
signed snapshot ensure the tag remains protected indefinitely after creation.

Just-in-time collection, short expiry, direct comparisons and separation of
duties reduce exposure, not eliminate it. GitHub offers no atomic policy-snapshot
and ref-create API. Stronger guarantees require a separately reviewed external
broker/freeze mechanism with additional trust/authority, not merely this CLI.
Before implementation/launch, independent reviewers and the owner must explicitly
accept the bounded administrative-race assumption or keep NO-GO. Do not advertise
absolute anti-replay/anti-forgery protection under compromised signer, database
or GitHub administration.

## Required implementation acceptance plan — no live paid tests

1. **Canonical crypto tests:** RFC vectors; altered payload/signature, wrong or
   revoked key, wrong domain/purpose, duplicate/unknown fields, Unicode edge
   cases, huge inputs, numeric precision, alternate base64, wrong signature
   length, invalid encodings and canonicalization mismatches must deny.
2. **Binding tests:** independently vary every repository/workflow/SHA/code/key
   digest, run, attempt, dispatcher, Environment, ruleset, ref, payload, pricing,
   ledger authority and epoch field. Verify denial before consumption/claim.
3. **Policy tests:** missing/redacted/null/nonempty bypass actors, wrong target,
   excludes, disabled/evaluate rules, missing update/deletion, incomplete parent
   pages, unknown/conflicting rules, unsafe reviews/branch policies and missing
   accepted reviewer access. No owner projection may conceal a conflict.
4. **Freshness tests:** exact expiry boundary, future issue time, collection
   duration, skew, database/verifier disagreement, pricing expiry and delayed
   approvals. Test expiration again immediately before claim, not only at fetch.
5. **Offline HTTP fixtures:** fixed-host GET-only collection, redirects,
   403/404/other failures, pagination, invalid/oversized responses, timeout and
   unexpected API shapes. Use fake transports only, never owner tokens.
6. **Isolated Postgres 16 acceptance:** apply future migration in disposable
   database/schema-only branch; inspect all ACLs/owners/defaults/memberships and
   SECURITY DEFINER definitions. Attempt direct DML/DDL, SET ROLE, registration
   from verifier, consumption from issuer and all coding functions. Require zero
   skipped tests, no production data or connection strings.
7. **Concurrency/replay:** eight and higher parallel consumers, duplicate runs
   with new nonces/keys, nonce reuse across runs/purposes, transaction aborts and
   lost commit responses. At most one committed success, no reset or retry.
8. **Cross-boundary fault injection:** terminate before/after registration,
   consumption commit, tag-object creation, ref creation and simulated provider
   send. Approved simulated model sees at most one call only after confirmed
   permanent claim. Reruns/cancellations never reuse consumed state.
9. **Workflow/static regression:** manual main-only attempt 1, exact checkout,
   protected independent approvals, pinned actions/keys and permission maps;
   verifier has no OpenAI key/write scope; paid job has no DB/owner/signing key;
   no automatic dispatch/merge/retry, activation toggles or coding path.
10. **Storage/incident tests:** forged artifacts/receipts, modified ledger bytes,
    clone/restore endpoint, stale epoch, credential misuse and key revocation.
    Prove restore uncertainty freezes execution rather than restoring authority.
11. **Redaction tests:** synthetic tokens, headers, raw bodies, private keys,
    database URLs and exception text never appear in logs, outputs or artifacts.
12. **Regression gates:** existing Bootstrap admission/concurrency tests and all
    five required CI checks pass on the future implementation head. Any live
    read-only acceptance needs separate approval; a paid canary is not a test
    prerequisite and remains separately authorized only after readiness GO.

## Review/implementation gates

- Independent design review first; record decisions on signer custody, ledger
  authority/restore policy, approval timing and explicit TOCTOU acceptance.
- Separate implementation PRs for canonical evidence/CLI, isolated ledger and
  verifier, then Bootstrap integration. No activation included in those PRs.
- Future roles, migrations, Environments, public keys and Secrets require their
  own reviewed configuration and owner authorization; none are created here.
- Revalidate live GitHub and Neon configuration, credential provenance/model
  entitlement and model/pricing window before considering launch. The existing
  pricing deadline must not be silently extended by this design.
- **Current decision: NO-GO for implementation activation and paid Bootstrap.**

## Sources and evidence limits

- [Existing Bootstrap proposal](dev-agent-bootstrap.md) and the repository SQL/
  rollout source linked above, reviewed at the baseline commit; source patterns
  do not establish deployed Neon privileges or durability.
- [GitHub ruleset read/visibility](https://docs.github.com/en/rest/repos/rules#get-a-repository-ruleset).
- [RFC 8785 JCS](https://www.rfc-editor.org/rfc/rfc8785) and
  [RFC 8032 Ed25519](https://www.rfc-editor.org/rfc/rfc8032).
- [PostgreSQL 16 constraints](https://www.postgresql.org/docs/16/ddl-constraints.html)
  and [SECURITY DEFINER safety](https://www.postgresql.org/docs/16/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY).
- [Neon restore](https://neon.com/docs/postgres/backup-restore/branch-restore).

No database connection, credential read, configuration change, workflow dispatch,
claim creation or paid request was performed to prepare this design.
