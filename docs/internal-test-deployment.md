# Private internal synthetic test deployment (prepared, not deployed)

**Status:** configuration and procedures are being verified locally and through branch CI. No cloud resources have been bought/provisioned, no deployment is authorized yet, and no test URL is claimed. Synthetic data/test accounts only; no live restaurant or integrations. AI review and tests are the demo review standard; independent human sign-off is not required. Authentication, CSRF, organization/location authorization, forced RLS, immutable audit/ledger and independent inventory approval still apply.

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

Apply cloud firewall restrictions too: TCP 80 for ACME/redirect, TCP 443 only from approved tester public IP CIDRs, no 5432/6379/8000/3000, no public SSH. Manage host via AWS Systems Manager with IMDSv2 required. Restrict any IPv6 ingress as well. Caddy independently checks the tester IP allowlist; never set `0.0.0.0/0` or `::/0`. HTTPS certificate issuance needs DNS to this public IP and ACME reachability. Private database/Redis ports must remain unpublished even temporarily.

The image uses `ENVIRONMENT=internal-demo`, secure HttpOnly cookies, HTTPS frontend/CORS, same-origin `/api` proxy, no API request access logs, and a visible synthetic-demo banner. Build-time API origin must match the chosen hostname; changing a runtime env variable alone cannot change a Next.js build. Runtime app/worker receive only app database/session/Redis secrets. Migration credentials are mounted only to the one-shot migrator and DB initializer. `/ready` verifies no superuser/BYPASSRLS runtime role.

Secrets are managed in AWS Secrets Manager, fetched using the host instance role into root-owned `/run` tmpfs, and mounted only into required containers. Compose file mounts are **not** a managed secret store by themselves. Files are readable by assigned non-root containers (0444), but the host directory is root-only (0700); host root and Docker administrators remain trusted. Do not place secrets in Compose env files, command arguments, shell history, GitHub logs or the repository. Restarting containers preserves mounts; reboot requires refetching secrets before Compose startup. Do not expose instance metadata or install cloud credentials inside application containers.

Photo uploads are disabled by fail-closed runtime behavior: the demo config has no scanner path and the normal backend rejects uploads with 503 outside development/test. Do not switch the environment to development or use a dummy executable to bypass it. Enabling uploads requires a separately reviewed scanner-equipped image, real clean/test-malware success/rejection tests, fresh signatures/monitoring and explicit config change; this deployment package does not enable them.

## Approval and deployment steps (execute only after owner approval)

1. Owner approves AWS region/budget, a controlled DNS hostname, tester IP CIDRs and the exact branch SHA. Provide scoped role access through AWS identity/SSO, not account root credentials or passwords in chat. No merge into main is required to deploy a separately approved test branch.
2. Provision the host and encrypted persistent disk, Systems Manager access and limited firewall above. Install Docker Engine with Compose v2, AWS CLI v2, Git and Python 3. Install security updates. Attach a role with `secretsmanager:GetSecretValue` limited to the runtime-secret ARN, plus necessary KMS decrypt if a customer-managed key is used. Account-provisioning/verification secret access belongs to the operator, not the application/worker. Confirm actual cloud security groups and public-port scan before opening access.
3. Create one runtime managed secret with exactly `postgres_password`, `app_password`, `migration_password`, `redis_password`, `session_secret`. Generate each independently with a cryptographically random URL-safe 48-byte token (32–128 characters); never use example passwords. Create a second operator-only test-account secret with `owner`, `gm`, `employee`, each containing a distinct synthetic `email` ending `@demo.example` and independent random `password` (32–128 characters). Deliver account passwords privately via an approved password manager to named testers, not via this document. Synthetic addresses do not receive email; invitation/reset SMTP is not claimed available.
4. Clone the working branch and pin an approved full commit SHA into a release directory. Record `git rev-parse HEAD`; do not use moving tags for rollback. Copy `ops/demo/host.env.example` to a root-owned host config outside the checkout, replace only non-secret host/CIDR/revision values. Point DNS to the stable IP.
5. As the authorized host operator, fetch runtime secrets:

   ```sh
   sudo python3 ops/demo/fetch_secrets.py \
     --secret-id APPROVED_RUNTIME_SECRET_ARN --region us-east-1 \
     --directory /run/chubby-demo-secrets
   ```

   The script uses AWS CLI identity, never prints values, validates exact keys, and refuses to overwrite existing secret files. Do not use shell tracing. Rotation must update database role passwords consistently; changing initialization secrets alone does not rotate existing roles. Reboot recovery refetches the same managed values.
6. Validate, build and start the **dedicated** file:

   ```sh
   sudo docker compose --env-file /etc/chubby-demo-host.env -f compose.internal-demo.yml config --quiet
   sudo docker compose --env-file /etc/chubby-demo-host.env -f compose.internal-demo.yml build
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

   If ingress allowlists prevent a server-origin HTTPS self-test, use a separate authorized verification container/workstation with the same tool, dependencies and operator-only secret access; do not broaden the public allowlist for convenience. Keep reports (IDs/results only) in private storage, not photo fixtures or passwords. Verify denied photo upload separately with an assigned draft count: it must return 503 with no object/metadata.
9. Restart `db redis api worker web ingress` without deleting volumes, wait for health, log in again and rerun the tool with `--check-restart /private-evidence/demo-check.json` and a new output path. Confirm the same approved session/decision, ledger and audit counts survive, with exactly one adjustment. Test host reboot after secure refetch separately; container restart is not host-reboot evidence.
10. Record actual URL, SHA, image IDs, trusted HTTPS and cookie results, firewall/network scan, role restrictions, migration revision, isolation/count/approval/replay checks, photo-disabled result and restart persistence. Fix failures before declaring ready. Provide the owner a test URL **only after these checks actually pass**. This is a private internal test deployment, not a live pilot.

## Backup and rollback

Before any later update, stop ingress/test actions and quiesce API/worker writes. Take a protected PostgreSQL custom dump and matching evidence/Redis-volume snapshot, preserve Caddy certificate volume, encrypt and record checksums. Docker volumes are persistence, not backups. Restore rehearsal uses a separate isolated stack/volume set, never overwrites current history. No real data is permitted.

Record the current release SHA and immutable `chubby-demo-api:SHA` / `chubby-demo-web:SHA` image IDs before building the next version. Retain the known-good images. Run migrations once before starting the new app; check compatibility before choosing rollback.

If an app-only update fails and old code supports the current schema: stop ingress/writers, return to the previous pinned release/config, use its already-built images (`up -d --no-build` with the same Compose project/volumes), and reverify health/HTTPS/login/isolation/persistence before reopening. Do not change secrets, reset accounts or delete volumes to mask errors.

If a migration/schema change cannot use old code, stop access and prefer a reviewed forward fix. **Never run destructive downgrades of 0004/0005, delete audit/ledger rows, or `docker compose down -v`.** A database restore can discard later test decisions: it requires explicit approval, an isolated restore verification and the matching storage snapshot. Document lost interval and reconciliation. Nothing here authorizes a rollback that overwrites data automatically.

## Current limitations and evidence

The combined branch is separate from main and the existing draft PRs; their tests are historical until rerun on this combined version. See [demo acceptance](platform-completion-plan.md#current-internal-demo-acceptance), [AI review](platform-ai-review.md) and [handoff](reviewer-owner-handoff.md). SMTP, scanner-certified uploads, HA/multi-host storage, physical iPad/camera, real staging restore and cloud URL remain unverified. Local Compose rehearsal is not hosting deployment.
