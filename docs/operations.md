# Development, staging, and recovery

## Local development

1. Install Python 3.12, Node.js 24.22.2, pnpm 11.25.0, and Docker Compose.
2. Copy `.env.example` to `.env`, replace placeholder secrets, and start `docker compose up --build`.
3. Compose initializes PostgreSQL with separate `chubby_migrator` and `chubby_app` non-superuser roles. The migration service alone receives the migration URL; API and worker use `chubby_app` with `NOBYPASSRLS`.
4. After migrations, provision the first owner once with `PYTHONPATH=backend .venv/bin/python -m app.bootstrap_owner`, using secure `BOOTSTRAP_OWNER_EMAIL` and `BOOTSTRAP_OWNER_PASSWORD` values.
5. Configure SMTP host/from and credentials before using invitation/reset email flows outside development/test. Production requires secure cookies, HTTPS origins, and a unique session secret.
6. `/health` reports process liveness. `/ready` verifies database connectivity, Redis connectivity, and the restricted application role. Stop with `docker compose down`; preserve the local database volume unless intentionally resetting local data.

## CI verification

`.github/workflows/sprint-1b.yml` is the authoritative mandatory test environment. The verification job provisions PostgreSQL 16 and Redis 7, creates restricted application and migration roles, applies Alembic with the migration role, and runs tests with the app role. A separate fixture-only PostgreSQL administrator account seeds isolated tenant fixtures. Missing `TEST_DATABASE_URL`, `TEST_MIGRATION_DATABASE_URL`, or `TEST_FIXTURE_DATABASE_URL` fails the job before pytest. The compose-runtime job builds and starts every service, waits on health checks, checks API/frontend response and the running worker, then performs graceful shutdown.

## AWS staging deployment

Staging is not yet deployed. Before deployment, provision isolated AWS resources with private networking, managed PostgreSQL and Redis, TLS termination, a container runtime, centralized logs, and managed secrets. Keep separate restricted migration-owner and application credentials; the application role must not own tenant tables and must have neither superuser nor RLS-bypass privileges. Store database, Redis, SMTP, cookie/session secrets in the managed secrets store. Build and scan immutable API/web images, run Alembic once as a migration task, deploy API/worker/web, and verify readiness, role logins, RLS isolation, backups, and alarms. Never expose PostgreSQL or Redis publicly. Record resource identifiers and deployment revision in the release record.

## Backup and restore

For managed PostgreSQL, enable automated point-in-time recovery and scheduled encrypted snapshots with retention appropriate to Chubby Group policy. Store snapshots in a separate protected backup boundary. Back up object storage separately if introduced. To restore, create an isolated database from the selected snapshot, verify integrity and migration revision, restore application secrets/configuration, run read-only smoke checks and tenant-isolation tests, then route traffic only after an owner validates the recovered data. The local Compose volume is not a backup.
