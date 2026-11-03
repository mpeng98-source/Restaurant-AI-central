# Initial database design

## Scope and conventions

Use UUID primary keys, UTC timestamps, foreign keys, and explicit active/status fields. Tenant-owned data includes `organization_id`; location-level operational data additionally includes `location_id`. The organization and location are separate records so additional locations require inserts only.

## Entities

| Table | Scope / purpose |
|---|---|
| organizations | Tenant root; unique slug and status. Seed Chubby Group (`chubby-group`). |
| locations | Organization-owned restaurant; unique location code within organization. Seed Burbank (`BURBANK-001`). |
| users | Login identity, normalized unique email, password hash, status, session invalidation version. |
| employees | Organization/location-associated employee profile; optional linked user. |
| roles | Configurable role catalog, platform or organization scoped. Seed six named roles. |
| permissions | Permission key and description catalog. |
| role_permissions | Role-to-permission mapping. |
| user_location_assignments | User's organization/location/role assignment, active dates/status. |
| devices | Organization/location scoped registered device metadata; no raw credentials. |
| audit_logs | Organization/location/user, action, entity reference, safe metadata, timestamp, request context. Append-only. |
| notifications | Recipient, organization/location scope, content, read/expiry timestamps. |
| ai_recommendations | Agent, recommendation, proposed action, scope, confidence, approval/execution statuses, timestamps. Inert. |
| approval_requests | Requester, approver, scope, payload reference, decision and timestamps, linked recommendation where applicable. |
| sessions | Hashed opaque token, user, created/expiry/revocation timestamps, safe client metadata. |

## Access and RLS

Enable and force RLS on tenant-owned tables. Policies compare `organization_id` with transaction-local `app.organization_id`; location tables also require `location_id` in the transaction-local allowed-location context. Missing context denies access. The API sets context only after verifying the session and assignments. Migrations/grants establish an application role that cannot bypass policies. Tests must connect using that role and attempt cross-tenant and cross-location reads/writes.

Application permission checks remain more specific than RLS: role permissions are configurable; corporate roles may be assigned across authorized locations; GMs are scoped to assigned locations; employee capabilities are limited to their own profile and explicitly assigned operational functions. RLS is intentionally a coarse database backstop.

## Seed data

Create organization Chubby Group, location Chubby Dumplings Burbank, and six role records: Platform Administrator, Corporate Owner, Corporate Operations Manager, Regional Manager, General Manager, Employee. The first privileged login must be provisioned via a one-time bootstrap command/environment input, never a hardcoded seed password.
