# Chubby AI platform architecture

## Sprint 01 foundation

```text
Responsive Next.js + TypeScript UI
              │ HTTPS / REST, cookie session
              ▼
FastAPI application ── authorization + validation + audit
       │                         │
       ▼                         ▼
PostgreSQL + SQLAlchemy      Redis / worker foundation
       │
       └── Alembic schema + transaction-scoped PostgreSQL RLS
```

The initial deployment is Chubby Group with Chubby Dumplings Burbank (`BURBANK-001`). Every location is a row associated with an organization. Users gain location access through explicit assignments and role permissions. The server derives tenant scope from the authenticated session and checks each requested location against assignments. RLS is a second enforcement layer, not a replacement for API authorization.

## Security boundaries

- Browser authentication uses an opaque, random, HttpOnly, SameSite cookie backed by server-side session records; passwords are Argon2id hashes. Production requires HTTPS and secure cookies.
- API dependencies load the user/session and enforce permission and location scope before returning operational records.
- PostgreSQL application connections use a non-owner, non-superuser role without `BYPASSRLS`. Each transaction sets organization, user, and authorized location context with transaction-local PostgreSQL settings; RLS policies fail closed when context is absent. A corporate owner receives an explicit organization-wide location context only after the API verifies that the location belongs to an assigned organization.
- Audit records are append-only through revoked application UPDATE/DELETE grants plus a database trigger. The separate migration owner remains subject to the trigger. Restricted fixture administration is isolated to CI.
- Secrets are supplied via environment for local development and a managed secrets provider for deployment.
- AI recommendations and approval requests are inert workflow records. No transaction execution integration is included.

## Initial modules

Organizations, locations, users, employees, roles, permissions, user-location assignments, devices, audit logs, notifications, AI recommendations, and approval requests. Operational tables carry organization and location scope where applicable. Platform-wide identity/role catalog rows may have no location; organization-owned data carries organization ID.

## Runtime and deployment

Docker Compose provides the web app, API, PostgreSQL, Redis, and worker foundation for local development. Production targets AWS managed PostgreSQL/Redis, container hosting, TLS, and managed secrets. Staging must use isolated AWS resources, managed secrets, migrations, backups, and the documented non-superuser RLS role. A local Compose environment is not staging.
