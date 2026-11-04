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
Propose an owner CLI and isolated Neon ledger, conditionally extended by the
independent external authority/restore witness specified below. The original
CLI-plus-Neon-only architecture is insufficient for latest-state restore detection.
No administrator-capable Actions token is proposed. No witness service exists by
virtue of this design; timing, witness coverage and deployment suitability remain
unproven and block implementation/activation readiness.

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
| Neon ledger | Durable local registration/consumption and unique constraints, cross-checked against external witness | Cannot establish restore-free authority from its own rows or authorize a paid call |
| External authority witness, proposed | Independent append-only checkpoint, operation generation, nonce/run burns and fresh signed integrity assertions | No OpenAI credential, owner GitHub credential, protected approval or paid-call authority; private key stays outside Actions |
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
4. CLI validates a locally pinned policy and fresh external authority assertion,
   displays a sanitized confirmation of run/SHA/nonce/expiry/purpose, signs evidence
   and follows the witness-first immutable registration protocol below.
   The CLI does not assert that pending Environment approval already occurred.
5. Independent reviewer approves the preflight job within the evidence's short
   lifetime. The verifier authenticates the envelope, checks live readable
   context/policy, external checkpoint continuity and lifetime guards, then follows
   the witness-first protocol and atomically consumes/commits the Neon record.
   No waiting/polling, renewal or automatic recovery loop is proposed: missing
   or expired evidence denies the run.
6. Only verifier success with exact run/SHA/envelope digest can unblock the
   existing Bootstrap job. Its existing protected Environment approval is still
   required, even if this means a second approval. Do not remove or weaken it.
7. Immediately before any claim, Bootstrap independently re-verifies the signed
   envelope, context, expiry, fresh external authority assertion and main SHA.
   It applies the lifetime guards before each mutation and before any paid send.
   GitHub's trusted same-run dependency
   must prove the isolated verifier committed that exact digest. Never accept a
   caller-supplied boolean, artifact, receipt or `needs` substitute as admission.
8. Preserve annotated tag-object creation then atomic permanent create-ref;
   confirm the returned exact ref/object before the sole paid request. A signature
   or consumed nonce alone never reaches the model endpoint. No cleanup deletes
   or moves the tag. No OpenAI credential enters the verifier job.

The short lifetime includes both approval waits. Delayed or insufficient-lifetime
approval denies; no new run or replacement evidence is automatic recovery.

### Five-minute operating budget and hard lifetime gates

The following is a **candidate staffed-session budget**, not a measured GitHub
service guarantee. Both reviewers must be available before issuance; no unattended
operation is assumed. The owner completes the existing <=30-second metadata
collection before `t0 = issued_at = collection_end`. Signing, registration and
human handoff occur after t0 and consume the same nonrenewable 300-second window.

| Phase after t0 | Target ceiling, seconds | Cumulative elapsed, seconds |
| --- | ---: | ---: |
| Owner confirmation/signing, witness check and immutable registration | 20 | 20 |
| First protected Environment approval | 20 | 40 |
| First runner queue/startup | 30 | 70 |
| Verifier checks, witness reservation and durable database consumption | 25 | 95 |
| Second protected Environment approval | 20 | 115 |
| Bootstrap runner queue/startup | 35 | 150 |
| Final signature/context/authority verification | 20 | 170 |
| Annotated tag-object and permanent ref creation (two <=30-second requests plus <=5-second fresh authority check between them) | 65 | 235 |

The remaining 65 seconds cover a five-second conservative clock allowance,
a 45-second post-claim safety reserve and 15 seconds of scheduling variability.
These are planning targets, not permission to exceed a hard lifetime gate.
All external-witness work below must fit these budgets; it receives no separate
or extended evidence lifetime. A provider request may start only while evidence
and pricing approval are still valid, with the required post-claim reserve.
Timeout/uncertain outcomes still permanently consume the opportunity.

Define conservative remaining lifetime `R = effective_expiry - latest trusted
current time - 5 seconds`; use the maximum of independently validated verifier,
database and witness times available at that boundary. Unknown time, larger
clock disagreement, expired evidence or `R` below a required threshold denies.
There is no expiry grace, renewal, replacement nonce or automatic retry.

| Critical boundary | Minimum R, seconds | Enforcement |
| --- | ---: | --- |
| Before signing/publishing evidence | 280 | Owner CLI checks before any registration |
| After confirmed registration / first approval handoff | 260 | CLI stops if acknowledgement is late; next job rechecks |
| First approval completed, before its queued startup | 240 | Reviewer timing target; checked retrospectively where trustworthy timestamps exist |
| Verifier runner starts | 210 | Automatic guard before verification or ledger/witness mutation |
| Immediately before consume request | 195 | Reserve <=10 seconds for consume/commit acknowledgement plus downstream budget |
| After confirmed consume and witness acknowledgement | 185 | No verifier success output unless sufficient time remains |
| Second approval completed, before Bootstrap queue | 165 | Reviewer timing target; next runner applies the mandatory automatic guard |
| Bootstrap runner starts | 130 | Deny before final verification |
| Before annotated tag-object creation | 110 | Reserve 65 seconds for claim phase plus 45 seconds |
| Before permanent create-ref request | 75 | Deny without sending if remaining time is insufficient |
| After confirmed create-ref | 45 | Reserve <=5 seconds for a fresh authority assertion and 40 seconds before paid start; denial retains the tag |
| Immediately before paid request | 40 | Recheck expiry/pricing/fresh authority; denial retains the permanent tag |

Approval/queue boundaries have no running script that can prevent a late human
approval. They are operational deadlines, not a substitute for automatic gates
at runner startup and before mutation. Do not invent unavailable GitHub approval
timestamps; missing timing telemetry blocks feasibility acceptance, while current
trusted-clock R checks still enforce denial. A late commit, timeout or late
approval never makes burned state reusable, even when no paid request occurred.

**Feasibility decision:** the current two-approval design is operationally
infeasible for unattended operation or any deployment whose representative queues
and approval response times cannot meet these guards reliably. It is **not yet
demonstrated feasible even for a coordinated session**. Do not implement/activate
this architecture on the assumption that two human approvals and hosted queues
will usually fit. If either timing acceptance or authority verification below
cannot fit, record OPERATIONALLY INFEASIBLE for that deployment and retain NO-GO.

#### Future non-paid timing acceptance — not dispatched by this PR

After separate authorization and implementation review, use the two actual
protected Environments, actual independent reviewers and production-equivalent
runner/dependency startup. Use only synthetic evidence and an isolated test
ledger/witness; replace tag creation and the model transport with non-writing
fakes. Simulate both claim requests with their full 30-second latency budgets
and the intervening five-second authority check as well as faster cases; zero-
latency fake claims alone cannot establish timing feasibility. The harness must
have no OpenAI key or GitHub ref-write path and must
verify identical approval configuration. Record synchronized issuance,
registration, both approval waits, queue/start, verifier consume/acknowledgement,
final validation and simulated claim timestamps. Do not count cached runner or
pre-approved-job results as cold-start evidence.

Require at least 20 coordinated non-paid sessions spanning quiet and busy
representative periods, plus deterministic delay injection at every phase.
Every session inside the stated operating envelope must pass each R boundary
and finish simulated claim by t0+235 seconds; do not discard unsuccessful samples.
Queue samples and operator availability must represent the intended deployment.
Inject 60/120/300-second queue delays, delayed approvals, witness/Neon cold starts,
clock disagreement, acknowledgement loss, exact threshold/expiry edges and
post-consumption delay. Every insufficient-lifetime case must deny before its
next prohibited action, with no refresh, re-consumption or paid call. Verify
consumed state remains burned. Finite samples are operational evidence, not a
future latency guarantee: a real late run must always deny. Failed representative
sessions block feasibility until a separately reviewed architecture is chosen.

#### Alternative requiring separate design review if timing fails

Front-load **both unchanged independent protected approvals and runner startup
before final evidence issuance**, then perform a just-in-time owner issuance.
This cannot be achieved merely by moving the existing paid job to an unprotected
Environment or reusing another job's approval. A candidate redesign keeps the
actual Bootstrap job behind its existing approval, lets it await a bounded,
run-bound handoff, and uses a separately isolated external verifier/broker for
durable consumption after both approvals. The broker has no OpenAI key or owner
GitHub/private signing key; any job-authentication and signed-receipt protocol,
new service trust boundary and permissions need separate review. The paid job
still independently verifies evidence, freshness and permanent claim ordering.
Do not provision a broker, change workflows, add credentials, implement polling
or claim this alternative is accepted here. Its shorter issuance-to-claim path
must independently pass non-paid acceptance; TTL stays <=300 seconds.


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
| Ledger | Pinned ledger-authority identifier/epoch, external witness identity, checkpoint sequence/digest and incarnation generation; not a caller-selected endpoint or database URL |
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


### External authority checkpoint and restore-event witness — prerequisite

A row inside Neon, its authority ID/epoch, WAL position, TLS certificate or content
hash is **not** an independent restore detector. A clone can copy them, and a
restore to the latest committed state can leave every ledger byte unchanged.
Neon alone is therefore insufficient for the required authority assurance.

Responsible operator: `mpeng98-source` as designated Ledger Authority Custodian
(stable identity must be pinned during separately reviewed enrollment).
Independent recovery approver: `mgpeng98-tech`, distinct from the custodian.
Neither role may self-approve recovery. The custodian must maintain the following
external witness in a separate authorization and durability domain from Neon and
GitHub Actions; no witness/private signing key or Neon management credential
enters Actions. Existing database issuer/verifier roles cannot reset that witness.

The proposed witness has append-only retained history, authenticated atomic
compare-and-swap, a monotonic sequence/hash chain, a distinct pinned signing key
and immutable nonce/run tombstones. Its authoritative checkpoint binds:
Neon organization/project/branch/endpoint/database identities and endpoint mapping,
ledger authority/epoch, independently observed database incarnation/restore
generation, schema/function/ACL fingerprints, last registration/consumption
sequence and digest, and the last fully observed control-plane operation frontier.
Checkpoint storage must not be restored or cloned together with Neon. GitHub
comments, artifacts, a file copied beside a database backup, or a caller-supplied
checkpoint are not trust anchors.

Before any future issuance, fetch or consumption, obtain a **fresh challenge-bound
witness assertion** tied to repository/run/attempt/SHA/evidence digest, current
checkpoint sequence, restore generation and clock, with a <=10-second lifetime
and within the evidence's existing R budget. Reject replayed or expired assertions,
wrong endpoint/authority, stale or regressing sequence, gaps, unknown operations,
pending restore/reset/endpoint reassignment, inconsistent digest, incomplete
pagination/history, failed witness authentication or unavailable witness. Compare
the configured endpoint against independently authenticated Neon management-plane
identity; do not trust identity values read solely from the selected SQL database.
Recheck authority immediately before claim; the paid job receives only a bounded
authenticated assertion, never a management/database credential. The restricted
consumer cannot mint its own authority assertion.

This adds a real external dependency to the original minimal design. A future
protocol and deployment must be reviewed; none exists or is enrolled by this PR.
Only a stored signed checkpoint without a fresh witness is insufficient. Fresh
challenge checks do not renew owner evidence, extend its expiry, consume the
nonce twice or restore a burned opportunity.

#### Cross-system atomicity and stale-state detection

Every registration and consumption must first reserve its exact operation in the
external witness using atomic nonce/run uniqueness, then apply the corresponding
Neon transaction, then advance the external checkpoint only after confirmed DB
commit and fresh identity/history checks. An external reservation is irrevocably
burned on uncertainty; success requires both acknowledgements. Do not attempt a
distributed rollback, rewind a checkpoint or reconstruct permission from a later
read-back. Pending witness intent, a missing DB record, or either side ahead of
the other freezes admission until independently approved reconciliation.
Thus restoring an older DB cannot erase the independent burn or permit replay,
even if copied rows claim the same authority ID/epoch. Neon still enforces its
local unique constraints; the permanent GitHub tag remains the paid-call barrier.
The witness is not a paid-execution permit and cannot replace protected approval.
The signed owner envelope binds the **pre-registration parent checkpoint**.
Fresh witness receipts bind the resulting exact envelope digest and operation
IDs and prove monotonic descendant continuity from that parent. Do not bind a
payload to a resulting checkpoint that itself hashes that payload (a circular
digest dependency). Unknown lineage or unrelated authority changes deny.

#### Restore to latest state without a subsequent ledger write

The custodian's destructive-operation gate must durably record a freeze and
advance the external incarnation generation **before** any restore, reset, clone
promotion or endpoint/database reassignment, including a restore to the latest
state. A next verification sees the generation/freeze even if no DB write occurs
and the data hash is identical. Out-of-band operations must additionally be
detected through a fresh, authenticated, complete management-plane operation/
incarnation history independent of SQL data. A known restore event always freezes;
matching post-restore contents do not automatically clear it.

For a clone at another endpoint, compare externally pinned project/branch/endpoint
identity. For a replacement behind the same hostname, require the independent
incarnation/operation history; hostname, copied authority rows and TLS alone
cannot distinguish it. For an in-place reset, reconcile both external operation
generation and the ledger/witness checkpoint, not just table contents.

**Coverage prerequisite:** all destructive paths, including console/API, snapshot
finalization, project/branch restore, endpoint movement, SQL reset/admin changes,
break-glass and provider-side recovery, must either pass the witness gate or have
a trusted independently complete event/incarnation signal. A periodic operations
listing is not automatically proof of completeness, freshness or absence of a
restore. Event retention gaps or a missed/delayed frontier mean UNKNOWN and deny;
a successful GET with no new entries must not be interpreted as proof of no
restore unless completeness through the checked instant is established.

The [Neon operations API](https://neon.com/docs/reference/api/operations/list-project-operations)
and [restore API](https://neon.com/docs/reference/api/branches/restore-project-branch)
provide relevant control-plane observations, but this review has **not established
a complete, tamper-evident, timely event/incarnation guarantee covering all these
paths**. Enrollment must obtain and independently review that assurance or an
equivalent enforceable external operation boundary. Existing owner privileges
outside that boundary, unobservable provider recovery or missing history leave
coverage UNKNOWN; no assertion may be issued and evidence cannot be accepted.

**Residual detection limit:** an unobserved restore to byte-identical latest
state with unchanged public endpoint identity is indistinguishable from no
restore to a content-only checker. A new random DB write/challenge, matching
hash or copied epoch does not solve that problem. The external recorded event/
incarnation is what detects it. If the provider and operation controls cannot
supply it, the architecture is infeasible for the stated restore-detection
requirement and remains NO-GO; do not weaken the requirement or claim detection.
Compromise of the witness, custodian/control plane or trusted provider can still
defeat the assumption. A destructive event after the last fresh assertion is
also a residual cross-system TOCTOU risk, never an atomic no-restore guarantee.

#### Mandatory freeze and independently approved recovery

Any uncertainty, pending operation, mismatch, restore/reset/clone promotion,
lost acknowledgement or stale witness freezes issuance, consumption and claim.
Do not reset nonce/run state, auto-renew evidence, replay old assertions, clear
tombstones, move/delete a tag or silently select a different database.

The custodian must reconcile independent retained witness intents/tombstones,
Neon records, full control-plane history, reviewed schema/ACL fingerprints,
GitHub run/approval/claim provenance and any authenticated provider cost evidence.
Tag absence or missing costs alone cannot establish an unused opportunity.
All possibly consumed records stay burned. Document cause, affected interval and
records, restored authority and new proposed checkpoint/epoch, unresolved
ambiguities and evidence of preserved uniqueness. The independent approver must
explicitly approve the recovery record and continuity/revocation decisions before
a reviewed enrollment change is permitted. Epoch change must carry forward all
historical nonce/run tombstones. Unknown billing/claim or missing authority
history cannot be resolved by authorizing another paid attempt.

No existing Neon permission, role, setting, checkpoint, management credential or
witness service is created or changed by this design revision.

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
duties reduce exposure, not eliminate it. The earliest policy read can precede
issuance by up to 30 seconds, so snapshot age includes that collection interval
as well as the <=300-second envelope lifetime and bounded clock uncertainty. GitHub offers no atomic policy-snapshot
and ref-create API. Likewise a fresh external witness assertion cannot atomically
lock Neon/provider restoration through a later GitHub claim; the latest-state
restore detection and residual coverage limits above still apply. Stronger guarantees require a separately reviewed external
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
    Restore byte-identical latest state with no subsequent ledger write: the
    external generation/freeze must deny despite equal DB hashes/IDs/epoch.
    Test older snapshots, cloned same-ID rows, endpoint replacement, stale or
    regressing checkpoints, forged/challenge-replayed assertions, pending
    witness intent, partial DB/witness commits and missing/delayed history.
    A provider event stream with unproven coverage must deny, even when empty.
    Verify irrevocable external burns across every fault point and recovery.
    Recovery cannot proceed without distinct operator/approver records and
    preserved historical nonce/run tombstones.
11. **Redaction tests:** synthetic tokens, headers, raw bodies, private keys,
    database URLs and exception text never appear in logs, outputs or artifacts.
12. **Regression gates:** existing Bootstrap admission/concurrency tests and all
    five required CI checks pass on the future implementation head. Any live
    read-only acceptance needs separate approval; a paid canary is not a test
    prerequisite and remains separately authorized only after readiness GO.

## Review/implementation gates

- Independent design review first; record decisions on signer custody, ledger
  authority/witness coverage and restore policy, measured approval timing and
  explicit TOCTOU acceptance. If representative timing or latest-state restore
  detection cannot meet the defined requirements, mark the architecture
  OPERATIONALLY INFEASIBLE and require a separately reviewed alternative.
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
