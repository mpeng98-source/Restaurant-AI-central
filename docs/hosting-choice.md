# Hosting choice for the private synthetic demo

## Decision and price-verification status

AWS account setup and pricing review are complete. The owner authorized one
private synthetic demo in `us-east-1` within a $50–60/month target. A single
`t3.medium` EC2 host has been created; Docker and Tailscale are installed, and
the host is connected to the owner's tailnet. No application containers,
managed application secrets, or tester credentials have been deployed. No
domain or fixed tester IP is required. The server security group has no inbound
rules; Tailscale shields-up remains enabled until the application and HTTPS
Serve endpoint are ready.

**Recommendation: one AWS EC2 Docker server, privately reached through
Tailscale, using its supplied `ts.net` HTTPS address.** This reuses the tested
Compose stack, restricted PostgreSQL/migration roles and AWS managed-secret boot
configuration. It avoids domain purchase, public application ports and changing
tester-IP allowlists. It is the simplest compatible deployment of *this existing
application*, not the simplest provider signup. A cloud operator is still needed
for host patching, backups and initial setup.

The managed alternative is **Render**, with separate frontend, API, worker,
PostgreSQL and Key Value services. Render reduces server maintenance and supplies
HTTPS hostnames, but is not a drop-in deployment: runtime/migration role
provisioning, private networking, cross-site cookies or same-origin routing,
database recovery, and secret injection need provider-specific implementation
and verification. A provider hostname alone does not restrict access to invited
testers. Do not silently replace PostgreSQL with SQLite or connect as a database
owner to make deployment easier.

In plain language: Render is easier to maintain once adapted, but adapting and
retesting this multi-service application is additional work. The single-server
option keeps the already-tested database controls and deployment structure.
Tailscale adds one app/sign-in per tester; if installing it is unacceptable,
choose a browser-only access design separately rather than exposing the private
demo publicly as a shortcut.

**AWS rates were checked by the owner through the AWS Pricing API on 2026-11-05.**
The EC2, gp3, snapshot, public IPv4, and Secrets Manager rates below are verified
for `us-east-1`, not a cap or invoice forecast. Render figures remain illustrative
and unverified. Usage-dependent transfer, API calls, snapshot growth and taxes
are additional.

| Monthly component, USD | Single EC2 Docker host | Managed Render planning allocation |
|---|---:|---:|
| Compute | 2 vCPU/4 GB t3.medium, 730 × $0.0416 = $30.37 | Frontend $7 + API $7 + worker $7 = $21; larger services may be needed |
| Database and Redis | Included in server compute; not separately managed | PostgreSQL allowance $19 + Key Value allowance $10 = $29 |
| Persistent storage | 80 GB gp3 × $0.08 = $6.40 | Disk allowance $2; database capacity/backup charges must be checked |
| Public IPv4 | 730 × $0.005 = $3.65 | Included hostname/routing assumed; confirm plan |
| Managed secrets | Two × $0.40 = $0.80, plus API calls | Service secret variables assumed included; confirm scope |
| Backups | 40 GB incremental snapshot allowance × $0.05 = $2 | Not established by allowance; confirm retention/restore pricing |
| Domain/DNS | $0: Tailscale supplies address | $0: provider supplies address |
| Private tester access | Tailscale noncommercial free-plan eligibility/limits must be checked | No private-access service included in estimate |
| **Subtotal before extras** | **$43.22; retain $50–60 budget** | **$52 illustrative floor; allow $60–100 until sized and priced** |

Both exclude taxes, paid operator labor, unusual egress, increasing backup
storage and capacity upgrades. EC2 needs standard CPU credit mode to avoid
unlimited credit charges. Snapshots are not a tested application-consistent backup.
Stopping EC2 does not stop disk/IP/snapshot billing. A free sleeping service or
expiring free database is unsuitable for persistence acceptance.

AWS rates were returned by `aws pricing get-products` in `us-east-1`:
Linux shared `t3.medium` $0.0416/hour; gp3 $0.08/GB-month; snapshots
$0.05/GB-month; in-use public IPv4 $0.005/hour; Secrets Manager $0.40/secret
plus $0.05/10,000 API requests. Official verification pages:
[EC2](https://aws.amazon.com/ec2/pricing/on-demand/),
[EBS](https://aws.amazon.com/ebs/pricing/),
[IPv4](https://aws.amazon.com/vpc/pricing/),
[Secrets Manager](https://aws.amazon.com/secrets-manager/pricing/),
[Render](https://render.com/pricing),
[Tailscale](https://tailscale.com/pricing).
The operator must record chosen region, service sizes, disk, backups, transfer,
secret/API charges, taxes and total from these pages/checkout before spending.
If Tailscale free use is ineligible or insufficient, recalculate first; do not
assume paid access is covered by a $0 estimate.

## What you must do, in order

1. Read this comparison. You do **not** need to buy a domain or find a fixed IP.
   Confirm a fresh checkout estimate before purchasing anything.
2. If choosing the recommended server, open `aws.amazon.com` yourself and select
   **Create an AWS Account**. Use an email you control; AWS asks for contact,
   payment-card and identity verification details. Enter these only on AWS, never
   in chat. For this demo choose the no-charge basic support option if available;
   do not select paid support or unrelated services.
3. Enable multifactor authentication on the account owner/root login. Keep root
   for account administration, not deployment. Have your operator configure a
   least-privilege deployment role and your ordinary admin sign-in (SSO/Identity
   Center or another supported temporary-role flow). SSO does not already exist
   just because you created an account. Never give anyone root passwords,
   MFA codes or permanent access keys.
4. In Billing, enable billing visibility and a monthly budget alert. Alerts are
   **not a spending cap**. Approve the final instance/storage/backup estimate and
   the operator's separate fee. Do not click instance launch yet.
5. Create a Tailscale account using its official site and your supported identity
   provider. Confirm noncommercial-plan eligibility. Invite only named testers.
   Each tester installs Tailscale on their device and signs in; changing home or
   mobile IP addresses do not require firewall changes. This is a requirement:
   the recommended demo is not a public browser link anyone can open.
6. Give the operator the approved AWS role and tester list through your identity
   and private administration tools. They register the server with Tailscale,
   enable tailnet HTTPS and tell you the actual `server.tailnet.ts.net` name.
   That name appears in public certificate-transparency records; use a generic
   server name, not a restaurant/person name. No restaurant data is needed.
7. Require a restricted tailnet policy: named testers can reach only this server's
   HTTPS port; testers cannot reach SSH/database/Redis/admin services or one
   another. Default broad tailnet access is not acceptance evidence. The operator
   must test an uninvited device is denied. **Never enable Tailscale Funnel**,
   which would make the application public.
8. Receive Owner/GM/Employee demo credentials privately through a password
   manager. Keep test credentials separate from AWS/Tailscale identities.
   Ask for the URL only after the operator supplies the verification results.

For the managed alternative, create an account at `render.com`, enable MFA and
enter billing there only. Do not connect your entire GitHub organization:
authorize only this repository if you later approve deployment. Do not create
services until the exact role/network/secret configuration and revised total
are reviewed. There is no tested Render deployment file in this package.

## What engineering can automate, after authorized access

Engineering can render/build the Docker configuration, run migrations with the
separate restricted migrator, fetch managed secrets using the instance role,
seed audited synthetic accounts through `chubby_app`, run HTTPS/isolation/
approval/replay tests, and verify persistence. The operator can automate host
creation, Docker installation and scheduled backups once the provider account,
scope and budget are authorized.

You must perform provider signup, card/identity/MFA entry, billing approval,
tester invitations and role grants. These cannot be impersonated or safely
entered by the coding agent. A CLI sign-in does not create an AWS account.
Cloud resources were created by the owner following the approved CloudShell
steps; this coding environment still has no provider credentials. Continue
operator actions only through the owner's authenticated AWS/Tailscale consoles.

## Prepared private-network deployment files

Use `compose.internal-demo.yml` **with**
`compose.internal-demo-tailnet.yml`, not the development Compose file. The
overlay replaces public ports with `127.0.0.1:9080` only. Tailscale Serve on the
host terminates HTTPS and proxies to this loopback endpoint. PostgreSQL/Redis,
API and web still have no public ports. The backend/frontend retain HTTPS origin,
secure cookies, same-origin routing, forced RLS and inventory approval controls.

The operator installs current official Docker/Tailscale packages, obtains the
actual tailnet hostname, and copies `ops/demo/host.tailnet.env.example` into the
root-owned host configuration. Set `DEMO_HOST` to that hostname *before building*
the frontend. Existing AWS managed-secret units remain required; local plaintext
env files are not a substitute for a managed secret store.

After authorized setup and managed-secret fetching:

```sh
sudo docker compose --env-file /etc/chubby-demo-host.env \
  -f compose.internal-demo.yml -f compose.internal-demo-tailnet.yml config --quiet
sudo docker compose --env-file /etc/chubby-demo-host.env \
  -f compose.internal-demo.yml -f compose.internal-demo-tailnet.yml build api
sudo docker compose --env-file /etc/chubby-demo-host.env \
  -f compose.internal-demo.yml -f compose.internal-demo-tailnet.yml build web
sudo docker compose --env-file /etc/chubby-demo-host.env \
  -f compose.internal-demo.yml -f compose.internal-demo-tailnet.yml up -d --wait
sudo tailscale serve --bg --https=443 http://127.0.0.1:9080
sudo tailscale serve status
```

Confirm current Serve syntax with the installed official CLI before execution;
the Tailscale integration has **not been deployed or end-to-end verified**.
Use HTTPS from an invited tester workstation for the existing credential-stdin
verification tool. It needs no database/admin secret. Do not add private Docker
subnets to a public allowlist or use insecure TLS to make a test pass.

The original [deployment runbook](internal-test-deployment.md) remains the source
for managed secrets, setup, persistent volumes, boot ordering and non-destructive
rollback. For this private variant, substitute the two-file Compose invocation
everywhere and use tailnet identity policy instead of public tester-IP rules.
Close public inbound 80/443 as well as database/Redis ports; administer through
SSM. Do not remove a Tailscale state directory or enable Funnel during rollback.

Acceptance still requires trusted HTTPS, invited/uninvited device checks,
secure cookies, organization/location denial, count/independent approval,
scanner-less upload rejection, restart and host-reboot persistence, managed
secret recovery and actual backup/rollback evidence. HTTPS through Serve is
expected, not yet a verified capability. Photos remain disabled. The earlier
hosted Compose tests do not prove this new Tailscale transport works.

Repository checks on 2026-11-05: eleven focused configuration tests passed;
the actual two-file Compose render confirmed loopback-only ingress, no published
database/Redis/API/web ports, HTTPS frontend origin and secure cookies.
`Caddyfile.tailnet` passed Caddy validation. The internal HTTP hop is loopback/
Docker only; TLS depends on Tailscale Serve and remains an end-to-end verification
gate. The owner checked AWS prices and reports that Tailscale's free plan covers
the intended use/testers. Tailscale policy tests passed in its console; runtime
access remains shielded until the HTTPS service is prepared.
