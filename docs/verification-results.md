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

**Local:** no PostgreSQL tests ran; all 18 integration cases skip because this workstation lacks PostgreSQL/Docker and the test database URLs. **GitHub Actions run 1:** actual PostgreSQL 16 services started, configuration checks and Alembic migration/revision checks passed. Pytest collected 21 tests with no skips; 19 passed and 2 failed. The failures were bad-password login audit insertion under RLS and an audit-trigger test that could not reach the trigger while RLS filtered owner updates. The other tenant isolation, self-only, assignment-write, app-role, pool-context, and append-only app-role checks passed.

## 8. GitHub Actions and Docker Compose results

GitHub Actions run 1 executed on Ubuntu 24.04 at commit `9d3284305543e73c052082c8fa8fd5c91b6f8f79` ([run](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41601138163)). Third-party Actions were pinned. PostgreSQL/Redis configuration checks, restricted-role provisioning, migrations, and revision checks passed. The backend/security step failed with 2 tests failing and 19 passing, so subsequent frontend steps were skipped. The Compose runtime job built all images and passed Compose configuration, but stack startup failed because the PostgreSQL container exited with code 3; readiness checks did not run. The shutdown cleanup step ran after failure.

The full stack was attempted on the GitHub runner. Compose validation and image builds passed, Redis started, but the PostgreSQL container exited during initialization. API, worker, web readiness and healthy-stack shutdown are therefore unverified. A workflow diagnostic was added to print PostgreSQL logs if startup fails again.

## 9. Errors and remaining limitations

- The offline full pnpm reinstall aborted because pnpm's non-interactive safeguard would not remove the pre-existing `node_modules` directory; it also reported local Node 24.22.1 versus the required 24.22.2. The lockfile-only frozen check and all frontend checks/build passed against the installed tree. CI pins the requested Node version.
- A Starlette/AnyIO `BlockingPortal` deprecation warning appears during pytest; it did not fail tests.
- No real SMTP provider is configured locally. Production invitation and password-reset delivery requires SMTP host/from/credentials.
- Initial hosted RLS checks exposed two test/application defects; fixes are prepared and require another hosted run. The Compose database initialization failure still needs its captured PostgreSQL logs and a passing rerun.
- No staging deployment was attempted.

## 10. Sprint 1 completion recommendation

**Do not approve Sprint 1 yet; do not begin Sprint 2.** The code, setup instructions, mandatory CI workflow, and real PostgreSQL test cases are present, but the Definition of Done requires actual owner/GM/employee login, RLS and audit tests, all mandatory CI checks, Compose startup, and health verification. None of those PostgreSQL/Compose/hosted CI acceptance runs can be claimed from this workspace. Approve only after both workflow jobs pass with the real PostgreSQL suite executing and the full Compose stack reaching healthy state.

## Final verification follow-up: repository readiness

- `.gitignore` excludes `.env` and `.env.*` while allowing `.env.example`, plus virtual environments, `node_modules`, generated builds, test output, local databases, and key/certificate files.
- `.env.example` contains empty secret and database URL fields. Backend settings, Alembic, Compose, and database initialization require environment-provided credentials. A tracked-file scan found no literal passwords, tokens, private keys, or credential-bearing URLs; test passwords are generated per run.
- The complete 53-file tree is published on the exact private remote supplied by the owner. Git CLI push is unavailable because its credential helper cannot read a username; the connected GitHub integration published the source and follow-up commits.
- GitHub Actions run 1 (commit `9d3284305543e73c052082c8fa8fd5c91b6f8f79`) ran against PostgreSQL 16 and Redis. Migrations passed; 19 tests passed and 2 failed. Run 2 (commit `47394e29f9611009299512f1d530c4fe48e5fd7f`) also applied migrations, with 19 passed and 2 failed due rate-limit state leaking between tests. Compose image builds passed, but PostgreSQL initialization failed because a shell-style `#` comment was sent as SQL.
- Fixes for those run-2 findings are in the current local source: the rate-limit test clears its isolated Redis state, and the init script uses a SQL `--` comment. Run 3 is pending publication and verification.
- Latest local pytest evidence remains 3 passed and 18 skipped because no real PostgreSQL or Redis service is available on this workstation. Do not count that as PostgreSQL verification. No hosted run has passed yet, no deployment occurred, and Sprint 2 remains blocked.
