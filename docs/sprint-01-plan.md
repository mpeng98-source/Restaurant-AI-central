# Sprint 01 implementation plan

## Repository inspection

The repository began empty: no source files, project configuration, or repository instructions were present. This plan and `AGENTS.md` establish the starting architecture and engineering constraints.

## Technical dependencies

- Frontend: Next.js App Router, React, TypeScript; responsive owner, GM, employee shell.
- API: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, psycopg.
- Security: Argon2id password hashing, opaque server-side sessions, permission/location authorization, rate limiting, append-only audit trail.
- Data: PostgreSQL 16 with forced RLS; Redis 7 for rate limits and worker queue foundation.
- Runtime: Docker Compose for local development; AWS-ready container/secrets configuration and staging/backup/restore documentation.
- Tests: pytest, HTTPX, isolated PostgreSQL integration tests using the restricted application role; frontend build/type validation.

## Task breakdown

1. **Foundation (current milestone):** project layout, Docker development stack, config validation, database models, initial Alembic migration, tenant/location RLS, seed catalog and organizational records, health/readiness endpoints, API/frontend shells.
2. **Authentication:** bootstrap owner, login/logout, password hashing, server-side session expiry, rate limiting, audit events, API auth tests.
3. **Authorization:** configurable role/permission mapping, location assignment enforcement, owner/GM/employee view scoping and cross-location tests.
4. **Core dashboard:** organization/location overview, authorized user management, activity and approval placeholders, responsive role-specific interfaces.
5. **Governance and operations:** notifications and approval/recommendation records; ensure no automatic execution; Docker/runtime hardening, staging, backup/restore and architecture guides.
6. **Acceptance:** complete test and security suites against PostgreSQL RLS, staging smoke checks, API docs, deployment and recovery evidence.

## Acceptance sequence

Every milestone receives focused automated coverage before moving forward. End-to-end acceptance requires an authenticated owner to view Chubby Group/Burbank and authorized activity, a GM limited to assigned restaurant data, and an employee limited to assigned functions and own information. Cross-location requests must fail even when IDs are modified. Staging acceptance is a separate deployment step and cannot be inferred from local Docker success.

## Current milestone caveat

The current repository has no pre-existing cloud account configuration or deployed staging environment. The first milestone can create an AWS-ready local foundation and instructions; staging deployment and production credentials require configured AWS infrastructure and secrets.
