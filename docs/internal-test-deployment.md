# Private internal synthetic test deployment (prepared, not deployed)

**Latest owner direction:** AWS setup is stopped. The owner has no AWS account,
SSO, domain or fixed tester IPs. Use [the revised hosting comparison and beginner
steps](hosting-choice.md) first. Its private Tailscale variant is prepared but not
deployed; the public-host/IP-allowlist instructions below are an alternative,
not prerequisites the owner is assumed to already possess. Current costs still
need live provider verification before purchase.

**Status:** preparation is complete and all five current-version hosted checks passed. The verified deployment candidate is `d64881aee6e09f990d57e54c1e083584bf575de2`; subsequent handoff updates are documentation only. On 2026-11-05 the owner approved AWS EC2 hosting and private synthetic deployment with a $50–60/month budget, and chose operator-executed deployment. No cloud resources have been bought/provisioned and no test URL is claimed. The operator still needs scoped AWS access, a controlled hostname and approved tester IPs. Synthetic data/test accounts only; no live restaurant or integrations. No merge is authorized. AI review and tests are the demo review standard; independent human sign-off is not required. Authentication, CSRF, organization/location authorization, forced RLS, immutable audit/ledger and independent inventory approval still apply.

**Execution responsibility:** the owner chose to assign a cloud operator to execute this runbook rather than provide an AWS session to this coding environment. That operator must obtain owner-approved scoped access, hostname and tester IPs privately; no cloud access has been granted here. Engineering can finish repository/CI work independently, but cannot claim operator deployment or provide a URL before the operator supplies actual verification evidence.

## Recommended host and estimated monthly cost

One **AWS EC2 Ubuntu x86-64 t3.medium instance in us-east-1**, running the dedicated Compose stack; encrypted 80 GB gp3 EBS; attached least-privilege instance role for AWS Secrets Manager; Caddy automatic HTTPS; PostgreSQL/Redis private container networks. This is low-cost single-host internal testing, not managed database HA or a production availability claim. Use CPU credit **standard** mode to cap burst charges and build images sequentially; check memory/disk/load before approving more capacity.

Budget estimate at 730 hours/month, USD, checked 2026-11-05:

| Component | Estimate/month |
|---|---:|
| t3.medium, 2 vCPU/4 GiB, ~$0.0416/hour | $30.37 |
| One public IPv4, ~$0.005/hour | $3.65 |
| 80 GB gp3, ~$0.08/GB-month | $6.40 |
| Two Secrets Manager secrets, ~$0.40 each | $0.80 |
| Snapshot storage allowance, about 40 GB at ~$0.05/GB-month | $2.00 |
| Optional Route 53 hosted zone | $0.50 |
| **Planning total** | **about $44/month; allow $50–60/month** |

Not a quote: excludes domain purchase/renewal, tax, unusual transfer/log/backup growth and optional capacity upgrades. Stopped instances still incur disk/IP/storage charges. No free-tier discount assumed. Confirm prices/region in AWS before purchase: [EC2 pricing](https://aws.amazon.com/ec2/pricing/on-demand/), [t3.medium rate reference](https://instances.vantage.sh/aws/ec2/t3.medium), [EBS](https://aws.amazon.com/ebs/pricing/), [VPC IPv4](https://aws.amazon.com/vpc/pricing/), [Secrets Manager](https://aws.amazon.com/secrets-manager/pricing/). Owner approval of budget, domain, tester IP ranges and scoped cloud access is required first.

## Security/configuration boundaries

Use **only `compose.internal-demo.yml`**, not the development `docker-compose.yml` and not an overlay that retains its public database ports. Only Caddy publishes 80/443. API/web have no host ports; PostgreSQL/Redis/worker/migrations use an internal Docker network. Redis requires authentication and persists AOF; PostgreSQL persists its data. Caddy certificates/configuration and private evidence persist in named volumes.

Apply cloud firewall restrictions too: TCP 80 for ACME/redirect, TCP 443 only from approved tester public IP CIDRs, no 5432/6379/8000/3000, no public SSH. Manage host via AWS Systems Manager; set EC2 metadata options `HttpTokens=required`, `HttpPutResponseHopLimit=1`, `HttpProtocolIpv6=disabled` and verify containers cannot obtain instance-profile credentials. The host must still fetch its scoped managed secrets. Restrict any IPv6 ingress as well. Caddy independently checks the tester IP allowlist; never set `0.0.0.0/0` or `::/0`. HTTPS certificate issuance needs DNS to this public IP and ACME reachability. Private database/Redis ports must remain unpublished even temporarily.

The image uses `ENVIRONMENT=internal-demo`, secure HttpOnly cookies, HTTPS frontend/CORS, same-origin `/api` proxy, no API request access logs, and a visible synthetic-demo banner. Build-time API origin must match the chosen hostname; changing a runtime env variable alone cannot change a Next.js build. Runtime app/worker receive only app database/session/Redis secrets. Migration credentials are mounted only to the one-shot migrator and DB initializer. `/ready` verifies no superuser/BYPASSRLS runtime role.

Secrets are managed in AWS Secrets Manager, fetched using the host instance role into root-owned `/run` tmpfs, and mounted only into required containers. Compose file mounts are **not** a managed secret store by themselves. Files are readable by assigned non-root containers (0444), but the host directory is root-only (0700); host root and Docker administrators remain trusted. Do not place secrets in Compose env files, command arguments, shell history, GitHub logs or the repository. Restarting containers preserves mounts; reboot requires refetching secrets before Compose startup. Do not expose instance metadata or install cloud credentials inside application containers.

The supplied systemd secret-fetch unit and Docker dependency drop-in order boot-time fetching **before Docker starts containers**. Do not rely on a manual refetch after Docker's `unless-stopped` restart has already run. These units are for the dedicated demo host only: making its Docker service depend on demo secret retrieval also blocks other Docker workloads on that host if retrieval fails. Cloud IAM/metadata, boot ordering and an actual host reboot still require post-approval verification.

Photo uploads are disabled by fail-closed runtime behavior: the demo config has no scanner path and the normal backend rejects uploads with 503 outside development/test. Do not switch the environment to development or use a dummy executable to bypass it. Enabling uploads requires a separately reviewed scanner-equipped image, real clean/test-malware success/rejection tests, fresh signatures/monitoring and explicit config change; this deployment package does not enable them.

## Approval and deployment steps (execute only after owner approval)

1. Owner approves AWS region/budget, a controlled DNS hostname, tester IP CIDRs and the exact branch SHA. Provide scoped role access through AWS identity/SSO, not account root credentials or passwords in chat. No merge into main is required to deploy a separately approved test branch.
2. Provision the host and encrypted persistent disk, Systems Manager access, metadata restrictions and limited firewall above. Install Docker Engine with Compose v2, AWS CLI v2, Git and Python 3. Install security updates. Attach a role with `secretsmanager:GetSecretValue` limited to the runtime-secret ARN, plus necessary KMS decrypt if a customer-managed key is used. Account-provisioning/verification secret access belongs to the operator, not the application/worker. Confirm actual cloud security groups, container metadata denial and public-port scan before opening access.
3. Create one runtime managed secret with exactly `postgres_password`, `app_password`, `migration_password`, `redis_password`, `session_secret`. Generate each independently with a cryptographically random URL-safe 48-byte token (32–128 characters); never use example passwords. Create a second operator-only test-account secret with `owner`, `gm`, `employee`, each containing a distinct synthetic `email` ending `@demo.example` and independent random `password` (32–128 characters). Deliver account passwords privately via an approved password manager to named testers, not via this document. Synthetic addresses do not receive email; invitation/reset SMTP is not claimed available.
4. Clone the working branch and pin an approved full commit SHA into a release directory. Record `git rev-parse HEAD`; do not use moving tags for rollback. Copy `ops/demo/host.env.example` to a root-owned host config outside the checkout, replace only non-secret host/CIDR/revision values. Point DNS to the stable IP.
5. As the authorized host operator, install `ops/demo/chubby-demo-secrets.service` as `/etc/systemd/system/chubby-demo-secrets.service` and `ops/demo/docker-secrets.conf` as `/etc/systemd/system/docker.service.d/chubby-demo-secrets.conf`. Set the approved release directory, runtime secret ARN and region in the root-owned host config; run `systemctl daemon-reload`. On the first boot with an empty secret directory, fetch runtime secrets through that unit:

   ```sh
   sudo systemctl start chubby-demo-secrets.service
   ```

   The unit runs `ops/demo/fetch_secrets.py` using AWS CLI instance identity, never prints values, validates exact keys, and refuses to overwrite existing secret files. `RemainAfterExit` prevents repeated starts this boot from refetching over active mounts. Do not separately run the fetcher over those files, restart the unit or use shell tracing. Rotation must update database role passwords consistently; changing initialization secrets alone does not rotate existing roles. Validate the unit and Docker dependency, then test a cold boot (fresh `/run`) before declaring reboot recovery verified. Keep an SSM recovery path available if IAM/DNS retrieval fails. Never delete database volumes or rotate passwords to work around failed boot.
6. Validate, build and start the **dedicated** file:

   ```sh
   sudo docker compose --env-file /etc/chubby-demo-host.env -f compose.internal-demo.yml config --quiet
   sudo docker compose --env-file /etc/chubby-demo-host.env -f compose.internal-demo.yml build api
   sudo docker compose --env-file /etc/chubby-demo-host.env -f compose.internal-demo.yml build web
   sudo docker compose --env-file /etc/chubby-demo-host.env -f compose.internal-demo.yml up -d --wait
   ```

   Check the one-shot migrator exits zero at `0005_inventory_pilot`, every persistent service healthy, HTTPS certificate trusted, unauthenticated API 401, disallowed tester IP 403, `/api/v1` functional and no public database/Redis/API/web ports. Use `alembic current` from the migration service and `/ready` internally. Never supply migration/admin URLs to API.
7. Explicitly provision one-time synthetic users through the **restricted app role**, with the operator-only secret piped on stdin:

   ```sh
   aws secretsmanager get-secret-value --secret-id APPROVED_ACCOUNT_SECRET_ARN \
     --region us-east-1 --query SecretString --output text --no-cli-pager |
     sudo docker compose --env-file /etc/chubby-demo-host.env -f compose.internal-demo.yml \
       exec -T api python -m app.demo_setup
   ```

   Use a shell with `set -o pipefail` so upstream secret-fetch failures are visible. This creates a clearly synthetic organization, two locations, another tenant denial target, Owner/GM/Employee users assigned to location A, and a synthetic ingredient. Password hashes only are stored; account creation is audited. Rerun refuses to overwrite users or history. Owner can access locations within their organization; GM/Employee must be denied location B and all other-tenant locations. Record returned non-secret IDs privately.
8. Before giving testers a URL, run the explicit HTTPS synthetic acceptance tool below. This performs login, secure-cookie checks, org/location denials, opening proposed by Owner and independently approved by GM, Employee count, GM review/approval, employee approval denial and idempotent replay. It does not infer quantities or use live data. Run only once on a fresh demo item; repeated openings correctly conflict. Subsequent persistence verification is read-only.

   ```sh
   aws secretsmanager get-secret-value --secret-id APPROVED_ACCOUNT_SECRET_ARN \
     --region us-east-1 --query SecretString --output text --no-cli-pager |
     sudo docker compose --env-file /etc/chubby-demo-host.env -f compose.internal-demo.yml \
       exec -T api python tools/verify_internal_demo.py \
       --base-url https://APPROVED_HOST --confirm-synthetic-actions --output /private-evidence/demo-check.json
   ```

   If ingress allowlists prevent a server-origin HTTPS self-test, use a separate authorized verification container/workstation with the same tool, dependencies and operator-only secret access; do not broaden the public allowlist for convenience. Keep reports (IDs/results only) in private storage, not photo fixtures or passwords. The tool also tries a valid synthetic PNG on the employee's assigned draft and requires 503. Separately confirm zero evidence metadata/objects under the restricted role.

   The workstation verifier imports only the shared synthetic credential/identity contract: it does **not** require a database URL, session signing secret or database network access. Install the repository's locked backend dependencies in a local virtual environment and run `backend/tools/verify_internal_demo.py` directly with the same HTTPS flags and a private output path, piping only the operator's account secret to stdin. It also requires the visible synthetic-demo banner before testing accounts; missing labels are a failure, not permission to exercise stock actions.
9. Restart `db redis api worker web ingress` without deleting volumes, wait for health, log in again and rerun the tool with `--check-restart /private-evidence/demo-check.json` and a new output path. The tool checks the same approved decision and exactly one unchanged adjustment, balances and audit references. Independently compare inventory/demo audit rows and ledger counts/digests before/after (login/logout legitimately add authentication audit records). Test host reboot with the boot-time fetch dependency separately; container restart is not host-reboot evidence.
10. Record actual URL, SHA, image IDs, trusted HTTPS and cookie results, firewall/network scan, role restrictions, migration revision, isolation/count/approval/replay checks, photo-disabled result and restart persistence. Fix failures before declaring ready. Provide the owner a test URL **only after these checks actually pass**. This is a private internal test deployment, not a live pilot.

## Backup and rollback

Before any later update, stop ingress/test actions and quiesce API/worker writes. Take a protected PostgreSQL custom dump and matching evidence/Redis-volume snapshot, preserve Caddy certificate volume, encrypt and record checksums. Docker volumes are persistence, not backups. Restore rehearsal uses a separate isolated stack/volume set, never overwrites current history. No real data is permitted.

Record the current release SHA and immutable `chubby-demo-api:SHA` / `chubby-demo-web:SHA` image IDs before building the next version. Retain the known-good images. Run migrations once before starting the new app; check compatibility before choosing rollback.

If an app-only update fails and old code supports the current schema: stop ingress/writers, return to the previous pinned release/config, use its already-built images (`up -d --no-build` with the same Compose project/volumes), and reverify health/HTTPS/login/isolation/persistence before reopening. Do not change secrets, reset accounts or delete volumes to mask errors.

If a migration/schema change cannot use old code, stop access and prefer a reviewed forward fix. **Never run destructive downgrades of 0004/0005, delete audit/ledger rows, or `docker compose down -v`.** A database restore can discard later test decisions: it requires explicit approval, an isolated restore verification and the matching storage snapshot. Document lost interval and reconciliation. Nothing here authorizes a rollback that overwrites data automatically.

## Current limitations and evidence

The combined branch is separate from main and the existing draft PRs; their tests are historical until rerun on this combined version. See [demo acceptance](platform-completion-plan.md#current-internal-demo-acceptance), [AI review](platform-ai-review.md) and [handoff](reviewer-owner-handoff.md). SMTP, scanner-certified uploads, HA/multi-host storage, physical iPad/camera, real staging restore and cloud URL remain unverified. Local Compose rehearsal is not hosting deployment.

Local synthetic checks used the verified non-root development image (Node 24.22.2, pnpm 11.25.0, Python 3.12.11). All 13 focused setup/configuration/restart-regression tests passed. Account setup's other-tenant audit initially failed a location foreign key; an explicit location flush fixed it, with actual PostgreSQL audit coverage. Demo namespace-derived slugs prevent test setups colliding with an existing synthetic demonstration, without overwriting it. The actual Caddy ingress file passed `caddy validate`; the boot-fetch unit passed `systemd-analyze verify`. These are configuration checks, not public certificate, AWS IAM or host-reboot evidence.

The local stack passed trusted **internal-CA** HTTPS Owner/GM/Employee login, secure cookies, location/tenant denials, explicit opening and independent approval, employee count, approval denial and replay. Scanner-less PNG upload returned 503 with zero evidence rows/JPEG objects. After service restarts, the same decision/adjustment/audit references survived; the two ledger rows and 11 location-scoped inventory/demo audit rows had the identical SHA-256 fingerprint `017a51d770b75caef4baa7b827684f64e3edae0e56c959cc0d5368a586ac058f`.

**Local environment limitation:** this agent host's Docker DNS returned private-network addresses to a container on another network, and did not resolve names from an internal-only network. Disposable local overrides supplied reachable addresses; after restart the proxy needed its changed address refreshed. Therefore this local result proves data persistence, **not unattended DNS/restart availability**. No fixed addresses/DNS workaround are in the deployment Compose file. The added manual hosted-CI rehearsal (`ops/demo/rehearse.py` in the existing verification workflow) exercises the dedicated file with ordinary Docker DNS, an ephemeral trusted internal CA, a Docker-subnet-only allowlist and restart without address overrides. It creates no hosting resources, uses no AWS/private account secrets and retains only non-secret test reports for seven days. Hosted outcomes must be recorded before claiming that rehearsal passed.

The first hosted private-stack rehearsal reached acceptance but failed on Redis restart. The launcher originally rewrote a Redis-owned file in sticky `/tmp` as root, which is incompatible with Linux protected-regular-file hardening (disabled on this local host). It now writes the 0600 configuration in a private 0700 `/run/chubby-redis` directory. The hosted restart rehearsal is the regression check; a prior local green result does not close this issue.

The next rehearsal exposed a **MEDIUM confirmed AI configuration-review finding: the tester-IP denial ran after Caddy's proxy handlers**, so it did not enforce the intended private perimeter. At preparation commit `a05bcc5f1b72d56078ee26b0d0231c3900ce434e`, `ops/demo/Caddyfile:2-3,9-14` configured a matcher/response alongside `handle`; `caddy adapt` reproduced both reverse proxies preceding the 403 response, and the hosted denial assertion failed. No cloud deployment existed; authentication and planned cloud firewall remain separate protections, not excuses to ignore this defect. The fix puts denial first inside an ordered `route`. The regression requires 403 for both `/` and `/api/v1/me` from a disallowed source, followed by allowed-source acceptance and restart. See [AI delta findings and fix evidence](platform-ai-review.md#private-internal-deployment-preparation-ai-engineering-delta-review); this is AI engineering review, not independent human approval.

**Fixed-code hosted evidence:** `3ee3d2e9e33bbeb13e7fb273fe2d837bdeb3635a`, [run 42108729359](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/42108729359). The dedicated private-stack job, development-agent security regressions, development Compose smoke and full repository/history secret scans passed. Its downloaded `internal-demo-verification` reports confirm ordinary Docker DNS without fixed addresses, trusted internal-CA HTTPS/secure cookies, all three synthetic logins, location/tenant denials, independent count/opening approval and replay, scanner-less 503, disallowed-source 403 on both web/API, and restart persistence. Two ledger rows and ten location-scoped inventory/demo audit rows retained fingerprint `e1cccdf36f50df326fbd511dedf7d83b8327c431321869647bee60ad1dcfd5c0`; Redis restart passed with Linux `fs.protected_regular=2`. The broader job executed **148 backend/PostgreSQL tests with zero failures/errors/skips**, isolated synthetic database restore, TypeScript, lint and build, but hit its 30-minute limit fetching Ubuntu WebKit dependencies from the slow Azure HTTP mirror. Browser scenarios/CLI did not execute; the overall run is cancelled, not green. The retry selects the official Ubuntu HTTPS archive without changing signed package verification, browser pins or required tests. It also masks the ephemeral test signing secret before publishing it through `GITHUB_ENV`; no real hosting secrets were involved. Reports are retained seven days; expired evidence requires rerunning, not assuming success.

## Plain-language owner checklist

1. **Approved:** AWS EC2 internal-test hosting and private deployment at $50–60/month. Nothing has been purchased; no reviewer hire is required for this synthetic demo. Remaining checks and scoped access are prerequisites, not permission to bypass them.
2. Assign a cloud operator (you, an existing administrator or a contractor) with AWS/Docker experience. Provide scoped AWS identity/SSO access, not root passwords or credentials in chat. Use the verified release above and confirm us-east-1. Any contractor fee or domain purchase is separate from the approved hosting budget.
3. Provide a hostname you control and the public IP addresses of the named testers. Authorize only those testers; PostgreSQL/Redis remain private.
4. Have the operator create the two managed secrets, give the test Owner/GM/Employee passwords privately to testers, and confirm no live restaurant data or integrations are used. Photos stay disabled.
5. After deployment authorization, require actual public HTTPS, firewall, login/isolation/count/approval, restart, boot-secret recovery and backup/rollback evidence before receiving a test URL. Decide separately about any later code merge or live restaurant pilot.

**Message to the assigned operator:** "Please deploy the pinned, tested private synthetic demo using this runbook on AWS EC2 in us-east-1, within the approved $50–60/month hosting budget. Obtain scoped access, my controlled hostname and tester IP list privately. Use managed secrets, HTTPS, restricted database roles and private PostgreSQL/Redis ports; keep uploads disabled. Do not merge code or use live restaurant data. Return the actual test URL, release SHA and evidence for login/isolation/count approvals, firewall/metadata denial, restart, boot-secret recovery and rollback readiness. Stop and report failed checks rather than marking them complete."

## Final hosted verification

At `d64881aee6e09f990d57e54c1e083584bf575de2`, [run 42116313526](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/42116313526) passed **all five jobs**. Downloaded inventory reports confirmed **155 backend/PostgreSQL tests and six WebKit scenarios, zero failures/errors/skips**; hosted logs confirmed **seven authenticated CLI commands**, TypeScript, lint/build, fresh/legacy migrations, isolated synthetic PostgreSQL restore, Compose health/privacy and repository/history secret scans. The earlier Ubuntu-download blockage is resolved by selecting the official signed HTTPS source stanzas, including mirror-file indirection; no browser tests or package-signature checks were bypassed.

Downloaded `internal-demo-verification` reports also verified the actual synthetic banner, trusted internal-CA HTTPS/secure cookies for Owner/GM/Employee, location/tenant denials, independent opening/count approval and replay, scanner-less 503, disallowed-source 403 for web/API, ordinary Docker DNS and restart persistence. Two ledger rows and ten location-scoped inventory/demo audit rows retained digest `594a3cfd9ff75272d12212abae571ce2d00fb7eaa49575cf3a36c6a530cf9711`; protected-regular-file hardening was 2. The workstation verifier starts without database/session credentials. Reports are retained seven days; download sanitized evidence before expiry or rerun it.

This closes the confirmed code/configuration findings and synthetic CI checks, **not cloud operational gates**. Public certificate/firewall/metadata restrictions, AWS managed-secret boot recovery, actual host reboot and operational backup/rollback still require the chosen operator's resources and evidence. Browser emulation is not physical iPad/camera acceptance; internal-CA HTTPS is not a hosted public certificate. No live pilot, resource provisioning or deployment is claimed.
