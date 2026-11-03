# Sprint 1B security model

## Permission matrix

| Role | Assigned location dashboard | Read location employee profiles | Invite users | Own employee profile | Own notifications/tasks | Read SOP |
|---|---:|---:|---:|---:|---:|---:|
| Corporate Owner | All locations in each assigned organization | Yes, in those organizations | Yes | Via signed-in identity | Not currently mapped | Not currently mapped |
| General Manager | Assigned locations | Yes, in assigned locations | Not granted | Yes | Yes | Not currently mapped |
| Employee | Not granted | No | No | Yes | Yes | Yes |

Each protected endpoint checks the session and its required permission on the server. Location access is checked against active user-location assignments. Corporate Owner access across locations is granted only within an organization attached to that owner. The `/me` endpoint returns only the signed-in user's identity and employee record.

## Database policies

- `organizations`: row organization ID must match `app.organization_id`.
- `locations`: organization must match, and location ID must be in `app.location_ids`; `app.can_read_all_locations` allows a verified owner to list locations in that organization.
- `employees`: own row by `app.user_id`, or organization/location scope with `app.can_read_location_employees` set by an authorized endpoint.
- `user_location_assignments`: reads are self or organization/location-scoped; inserts can create only the current user assignment in the scoped organization/location. The app has no assignment update/delete RLS policy. Role and permission catalogs are read-only to the app role.
- `devices`, `ai_recommendations`, `approval_requests`: organization and authorized location must match.
- `notifications`: row `user_id` must match `app.user_id`; location membership alone does not grant access to another person's notification.
- `invitations`: lookup by token digest or authorized organization; writes require organization context. `invitation_locations` requires the invitation ID for token acceptance or authorized organization/location scope.
- `users`: self, or normalized login email for authentication lookup. Writes are restricted to `app.user_id`.
- `sessions`: token digest lookup or own user rows; inserts/updates require own user context.
- `password_reset_tokens`: token digest lookup or own user rows; writes require own user context.
- `audit_logs`: reads are scoped to organization and locations. Inserts require tenant scope or a system/auth event with no tenant and, when present, the current user. The app role has no UPDATE/DELETE and a trigger rejects mutation even for the migration owner.
- Role and permission catalogs are global read catalogs only; application writes to those catalogs and `alembic_version` are revoked.

All tenant tables use both `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`. Application and migration roles are separate `NOSUPERUSER NOBYPASSRLS` logins. The CI-only fixture administrator exists to seed test cases; API/RLS assertions run as `chubby_app`.

## Authentication

Passwords are Argon2id hashes. Invite and reset secrets are random one-use tokens stored only as peppered HMAC digests and expire. Token claims are atomic to prevent concurrent replay. Sessions use random opaque server-side tokens in an HttpOnly, Secure-in-production, SameSite=Strict cookie. A separate CSRF cookie and `X-CSRF-Token` header are checked for state-changing authenticated calls. Logout and password reset revoke active sessions. Redis enforces a per-email-and-source rate limit. Public registration is not routed.
