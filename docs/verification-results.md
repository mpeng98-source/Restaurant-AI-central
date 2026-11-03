# Sprint 1B security and runtime remediation report

**Run date:** 2026-11-02
**Assessment:** Sprint 1 remains incomplete. Keep Sprint 2 and inventory work on hold.

## 1. Files changed

- Authentication/security: `backend/app/auth.py`, `authorization.py`, `bootstrap_owner.py`, `config.py`, `main.py`, `models.py`, `security.py`, `worker.py`.
- Database/runtime: `backend/migrations/versions/0001_foundation.py`, `backend/init-db.sh`, `docker-compose.yml`.
- Verification: `backend/tests/conftest.py`, `test_api.py`, `test_auth_authorization.py`, `test_postgres_security.py`, `.github/workflows/sprint-1b.yml`.
- Frontend: `frontend/app/page.tsx`, `frontend/app/dashboard/page.tsx`, `frontend/app/forgot-password/page.tsx`, `frontend/app/reset-password/page.tsx`, `frontend/app/accept-invitation/page.tsx`, `frontend/app/styles.css`, `frontend/tests/smoke.mjs`.
- Setup/docs: `.env.example`, `README.md`, `docs/architecture.md`, `docs/operations.md`, `docs/security-model.md`, this report.

Python and frontend dependency lock versions were retained. `.nvmrc` targets Node 24.22.2. The initial local commit contains the implementation. The exact private GitHub remote supplied by the owner is configured; hosted verification remains pending.

## 2. Environment and dependency setup

- macOS 26.6.2, Apple Silicon (`arm64`). System Python is 3.9.6; the workspace Python 3.12.14 was used.
- Node.js is available from the workspace bundle at 24.22.1; the project/CI pin is 24.22.2. This one-patch-version mismatch produced an engine warning locally.
- pnpm 11.25.0 is available in the workspace bundle; pip and the pre-existing Python virtual environment are available. Homebrew, system npm, Docker/Compose, PostgreSQL client/server tools, and Redis server are absent from PATH.
- Python exact pins remain in `backend/requirements.lock`; frontend direct dependencies and resolution remain in `frontend/package.json` and `frontend/pnpm-lock.yaml`. Pytest configuration is `backend/pyproject.toml`; frontend checks are configured in `frontend`.
- `.env.example` contains local placeholders only. It documents separate application and migration URLs, CORS, cookies, Redis, and SMTP settings.

## 3. Authentication implementation

- Public registration is absent. An authorized owner can issue scoped, expiring invitations; invite tokens are stored as peppered HMAC digests and accepted once. Production sends invitation links through configured SMTP; development/test returns the token to facilitate local setup and tests.
- Passwords use Argon2id. Reset tokens are single-use, expire, are claimed atomically to prevent concurrent replay, and are stored as HMAC digests. A reset changes the password and revokes the user's active sessions. Production reset messages use SMTP; responses do not disclose whether an account exists.
- Login uses Redis rate limits keyed by normalized email and source address. Sessions are random opaque server-side records with expiry and revocation. The session cookie is HttpOnly, SameSite=Strict, and Secure when `COOKIE_SECURE` is enabled; production settings require Secure cookies, HTTPS origins, a unique 32-byte session secret, and SMTP configuration.
- State-changing authenticated requests check the separate CSRF cookie against `X-CSRF-Token`. Logout revokes the server session and clears both cookies.
- `backend/app/bootstrap_owner.py` provides a one-time, explicit Corporate Owner bootstrap with no hard-coded credentials.

## 4. Permission matrix

| Role | Dashboard | Employee profiles at location | Invite users | Own records/functions |
|---|---|---|---|---|
| Corporate Owner | All locations in each assigned organization | Yes | Yes | Signed-in identity |
| General Manager | Assigned locations only | Yes, assigned locations | No | Profile, notifications, tasks |
| Employee | No dashboard permission | No | No | Profile, notifications, tasks, SOP |

Authorization runs on the server for every protected route. Corporate Owner expansion checks that the requested location belongs to an organization assigned to that owner. The frontend does not grant permissions. Detailed permission and policy descriptions are in [security-model.md](security-model.md).

## 5. Database changes and RLS policies

The initial migration defines sessions, invitations, invitation locations, password-reset tokens, role/permission mappings, and tenant operational tables, then enables and forces RLS. This remains the single initial migration because the repository had no deployed database or prior migration history. The migration now requires `MIGRATION_DATABASE_URL` and refuses to fall back to the application account.

Compose/CI create separate `chubby_migrator` and `chubby_app` non-superuser, non-`BYPASSRLS` roles. The app role receives read-only access to role/permission catalogs and Alembic version state. Assignment RLS permits scoped reads and self-assignment inserts only; it has no app update/delete policies. Notifications are self-only. Employee rows require self identity or an endpoint-set employee-read context. Location rows require the tenant and location context, with a verified owner-only organization-wide read context. Audit rows are tenant-readable and append-only; the app has no update/delete privileges and a trigger blocks mutation even for the migration owner.

The application API URL defaults to `chubby_app`. `/ready` also rejects an API database connection if it is not the restricted `chubby_app` role.

## 6. Commands executed and successful checks

- `PYTHONPATH=backend .venv/bin/python -c 'import fastapi, sqlalchemy, alembic, psycopg, redis, argon2, app.models, app.auth, app.authorization'` — passed.
- `.venv/bin/python -m pip check` — passed; no broken requirements.
- `PYTHONPYCACHEPREFIX=/private/tmp/chubby-pycache .venv/bin/python -m compileall -q backend/app backend/migrations backend/tests` — passed.
- `.venv/bin/python -m pytest -c backend/pyproject.toml -q -rs` — **3 passed, 18 skipped**. The 18 skips are real PostgreSQL/auth integration cases requiring database URLs and services; no mocked success was substituted.
- `MIGRATION_DATABASE_URL=postgresql+psycopg://chubby_migrator:<redacted>@localhost:5432/chubby ../.venv/bin/python -m alembic upgrade head --sql` from `backend/` — passed static SQL generation (450 lines). It did not connect to PostgreSQL or execute a migration.
- `pnpm --dir frontend install --lockfile-only --frozen-lockfile --offline` — passed lockfile validation. A full offline install attempt aborted at pnpm’s no-TTY safeguard when it tried to remove the existing `node_modules` directory; no existing dependencies were removed. pnpm warned that local Node 24.22.1 is below the project pin 24.22.2.
- Frontend TypeScript `tsc --noEmit` — passed.
- Frontend ESLint — passed.
- Frontend `next build` — passed for `/`, `/dashboard`, `/forgot-password`, `/reset-password`, and `/accept-invitation`.
- Started the production frontend locally and ran `BASE_URL=http://127.0.0.1:3010 node tests/smoke.mjs` — passed for login and dashboard HTTP routes.
- Started Uvicorn locally; `/health` returned 200 and unauthenticated `/api/v1/me` returned 401. Server shutdown was clean. This did not exercise readiness dependencies.
- Parsed `docker-compose.yml` and the GitHub Actions YAML with PyYAML; parsed frontend `package.json` and `tsconfig.json` as JSON — passed. This is syntax parsing, not `docker compose config` validation.

## 7. Actual PostgreSQL test results

**No PostgreSQL tests executed.** All 18 integration cases were skipped because there is no PostgreSQL/Docker service and no `TEST_DATABASE_URL`, `TEST_MIGRATION_DATABASE_URL`, or `TEST_FIXTURE_DATABASE_URL` configured locally. This includes role logins, invitation/reset flows, permission enforcement, cross-organization/location access, employee self-only access, missing tenant/location context, app-role restrictions, assignment write restrictions, audit immutability, and pool context isolation. The static migration SQL generation is not a PostgreSQL migration result.

## 8. GitHub Actions and Docker Compose results

The workflow is configured but **has not run on GitHub**. It pins third-party Actions to reviewed commit SHAs, provisions PostgreSQL/Redis, fails before pytest if any required PostgreSQL or Redis configuration is absent, verifies both service connections, applies migrations as `chubby_migrator`, writes a JUnit report, and fails if any test is skipped. Tests run through `chubby_app`; a separate job starts the Compose services. The private remote is configured, but the complete project tree has not yet been published and no hosted workflow run is available.

Docker Compose was **not executed**. Docker is unavailable. Therefore actual Compose validation, PostgreSQL and Redis startup, migration execution, API readiness with real services, frontend/worker container startup, container health, and graceful stack shutdown remain unverified. Local YAML parsing is the only Compose verification performed here.

## 9. Errors and remaining limitations

- The offline full pnpm reinstall aborted because pnpm's non-interactive safeguard would not remove the pre-existing `node_modules` directory; it also reported local Node 24.22.1 versus the required 24.22.2. The lockfile-only frozen check and all frontend checks/build passed against the installed tree. CI pins the requested Node version.
- A Starlette/AnyIO `BlockingPortal` deprecation warning appears during pytest; it did not fail tests.
- No real SMTP provider is configured locally. Production invitation and password-reset delivery requires SMTP host/from/credentials.
- Readiness, database connectivity, Redis connectivity, PostgreSQL policies, and CI runtime behavior need execution in the Docker/GitHub-hosted environment.
- No staging deployment was attempted.

## 10. Sprint 1 completion recommendation

**Do not approve Sprint 1 yet; do not begin Sprint 2.** The code, setup instructions, mandatory CI workflow, and real PostgreSQL test cases are present, but the Definition of Done requires actual owner/GM/employee login, RLS and audit tests, all mandatory CI checks, Compose startup, and health verification. None of those PostgreSQL/Compose/hosted CI acceptance runs can be claimed from this workspace. Approve only after both workflow jobs pass with the real PostgreSQL suite executing and the full Compose stack reaching healthy state.

## Final verification follow-up: repository readiness

- `.gitignore` excludes `.env` and `.env.*` while allowing `.env.example`, plus virtual environments, `node_modules`, generated builds, test output, local databases, and key/certificate files. Ignore behavior was checked for the relevant paths.
- `.env.example` contains empty secret and database URL fields. Backend settings, Alembic, Compose, and database initialization now require credentials from the local environment; insecure database and session-secret fallbacks were removed. No actual API keys or production credentials are intended to be committed.
- The local branch has a root commit. The exact supplied `origin` is `https://github.com/mpeng98-source/Restaurant-AI-central.git`. Git CLI push failed because the environment could not read a GitHub username from its credential helper.
- The connected GitHub integration created a bootstrap commit containing `.gitignore`, but the complete project tree is not yet on GitHub. The first upload review found local fallback database passwords in `backend/init-db.sh`; those literal fallbacks were removed, as were defaults in backend settings, Alembic, and Compose. Review also flagged password values passed as psql command-line variables. The script now reads required passwords with psql `\getenv`, uses psql SQL-literal quoting for the fixed role password clauses, validates the fixed database name, disables psql startup files and query echo, and suppresses statement/error/duration logging for the role-creation session. Static shell and content checks passed. The connected GitHub integration accepted the revised script blob. Full-tree review then found a reusable literal test password in `backend/tests/conftest.py`; the shared test fixture and invitation/reset tests now generate per-run random passwords. A credential-like URL in this report was redacted. The complete tree has not yet been published or run in hosted CI.
- The latest local pytest run passed 3 tests and skipped 18 PostgreSQL integration cases because no real test database is configured; frontend checks/build and local API smoke checks passed as recorded above. No actual PostgreSQL migration, RLS suite, Redis readiness, Docker Compose runtime, or GitHub-hosted workflow run has been executed.
- Sprint 1 remains incomplete. Keep Sprint 2 and inventory work blocked until the complete repository is published and all mandatory hosted PostgreSQL and Compose checks pass.
