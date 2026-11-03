# Sprint 1B security and runtime remediation report

**Run date:** 2026-11-03
**Assessment:** Sprint 1B technical acceptance passed in hosted CI. Sprint 2 remains on hold as instructed.

## 1. Files changed

- Authentication/security: `backend/app/auth.py`, `authorization.py`, `bootstrap_owner.py`, `config.py`, `main.py`, `models.py`, `security.py`, `worker.py`.
- Database/runtime: `backend/migrations/versions/0001_foundation.py`, `backend/init-db.sh`, `docker-compose.yml`.
- Verification: `backend/tests/conftest.py`, `test_api.py`, `test_auth_authorization.py`, `test_postgres_security.py`, `.github/workflows/sprint-1b.yml`.
- Frontend: `frontend/app/page.tsx`, `frontend/app/dashboard/page.tsx`, `frontend/app/forgot-password/page.tsx`, `frontend/app/reset-password/page.tsx`, `frontend/app/accept-invitation/page.tsx`, `frontend/app/styles.css`, `frontend/tests/smoke.mjs`.
- Setup/docs: `.env.example`, `README.md`, `docs/architecture.md`, `docs/operations.md`, `docs/security-model.md`, this report.

Python and frontend dependency lock versions were retained. `.nvmrc` targets Node 24.22.2. The initial local commit contains the implementation. The exact private GitHub remote supplied by the owner is connected through the GitHub integration; hosted verification is recorded in sections 7–8.

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

**Local:** no PostgreSQL integration tests ran (3 passed, 18 skipped) because this workstation lacks PostgreSQL/Docker. **GitHub Actions run 3:** real PostgreSQL 16 and Redis services became healthy, migration revision `0001_foundation` applied, and all 21 collected backend tests passed with 0 failures and 0 skips. This included Owner/GM/Employee login, bad-password rejection, invitation acceptance and replay rejection, password reset expiry/single-use/session revocation, logout, CSRF, login rate limiting, role and location authorization, organization/location isolation, missing tenant context, restricted app role, assignment write restrictions, audit immutability, and pool-context isolation.

## 8. GitHub Actions and Docker Compose results

The final hosted verification ran on Ubuntu 24.04 at commit `272858507744362e61b905b597302c053a96c3e5` ([GitHub Actions run 41602836978](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41602836978)). Both jobs passed. Third-party Actions are pinned to reviewed commit SHAs. The backend job passed restricted-role provisioning, PostgreSQL/Redis connectivity, Alembic upgrade and revision check, 21 backend/auth/RLS tests (0 failed, 0 skipped), TypeScript, ESLint, production build, and `docker compose config --quiet`. The Docker Compose runtime job passed Compose validation, built and started the complete stack, applied migration `0001_foundation`, confirmed PostgreSQL and Redis, and reported `db`, `redis`, `api`, `worker`, and `web` healthy. `/health` returned `{"status":"ok"}`, `/ready` returned `{"status":"ready"}`, frontend returned HTTP success, and unauthenticated `/api/v1/me` returned 401. Graceful `docker compose down` completed successfully.

## 9. Errors and remaining limitations

- The offline full pnpm reinstall aborted because pnpm's non-interactive safeguard would not remove the pre-existing `node_modules` directory; it also reported local Node 24.22.1 versus the required 24.22.2. The lockfile-only frozen check and all frontend checks/build passed against the installed tree. CI pins the requested Node version.
- A Starlette/AnyIO `BlockingPortal` deprecation warning appears during pytest; it did not fail tests.
- Earlier hosted attempts exposed two RLS test/application defects, shared Redis rate-limit state, a SQL heredoc comment, missing ephemeral Compose validation values, and a missing `SESSION_SECRET` for the migration container. These were corrected and the final hosted run passed.
- No SMTP provider is configured for production invitation/password-reset delivery; the hosted tests exercise the test/development token flow. No deployment was attempted.

## 10. Sprint 1 completion recommendation

**The Sprint 1B technical acceptance suite passed in hosted CI.** The required authentication, authorization, real PostgreSQL RLS, audit, frontend, Compose startup/readiness, and shutdown checks all passed on the hosted CI run recorded in section 8. Sprint 2 and inventory work remain on hold as instructed; no deployment was attempted. Production readiness is not claimed because SMTP delivery and production deployment/configuration were not exercised.

## Final verification follow-up: repository readiness

- `.gitignore` excludes `.env` and `.env.*` while allowing `.env.example`, plus virtual environments, `node_modules`, generated builds, test output, local databases, and key/certificate files.
- `.env.example` contains empty secret and database URL fields. Backend settings, Alembic, Compose, and database initialization require environment-provided credentials. A tracked-file scan found no literal passwords, tokens, private keys, or credential-bearing URLs; test passwords are generated per run.
- The initialization review flagged fallback password patterns and password values passed in psql command-line arguments in the earlier script. The current script has no credential fallback, requires both password variables, fixes the database name to `chubby`, reads passwords from the process environment with psql `\getenv`, and uses psql's quoted variable expansion for fixed role statements. Role identifiers are literal constants; there is no user-controlled identifier interpolation. psql is quiet and does not load a user rc file, and PostgreSQL statement/error/duration logging is suppressed for the role-creation session. The final SQL heredoc comment uses SQL `--`, avoiding the previous `#` syntax error.
- The complete 53-file tree is published on the exact private remote supplied by the owner. Git CLI push is unavailable because its credential helper cannot read a username; the connected GitHub integration published the source and follow-up commits.
- GitHub Actions run 3 is at commit `272858507744362e61b905b597302c053a96c3e5`: 21 passed, 0 failed, 0 skipped; migrations, frontend checks/build, Compose startup, all five service health checks, `/health`, `/ready`, unauthenticated access rejection, and graceful shutdown passed. Earlier failed attempts are retained in sections 7–9 for traceability.
- Local PostgreSQL integration cases remain unexecuted: local pytest reports 3 passed, 18 skipped because PostgreSQL/Docker are unavailable. This does not replace or contradict the final hosted verification.

## 11. Final hosted verification and repository secret audit

Earlier runs recorded in sections 7–9 failed on specific test, workflow, and Compose setup defects. Those are historical results. The remediation run at commit `868c44d14fe1afe0912591f06aa6862a5a6fd6ac` passed both required jobs: [GitHub Actions run 41603446968](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41603446968). PostgreSQL 16 and Redis connected; Alembic migration `0001_foundation` succeeded; 21 backend/authentication/authorization/RLS tests passed with 0 failures and 0 skips; TypeScript, ESLint, production build, Compose startup, service health checks, `/health`, `/ready`, unauthenticated API rejection (401), and graceful shutdown all passed.

A later audit run at commit `a553d5a9bf265ea6d9b4100e45d5550f0948dc47` passed all three CI jobs: [GitHub Actions run 41605747622](https://github.com/mpeng98-source/Restaurant-AI-central/actions/runs/41605747622). The Gitleaks v8.30.1 image is pinned by digest. Its redacted current-tree scan and full reachable-history scan both reported “no leaks found.” A separate history-path check found no committed `.env` files; .env.example is the only tracked environment file and contains placeholders, not credentials. The tracked file scan also found no private key/certificate files or credential-bearing connection strings. No credential rotation or history rewrite was indicated or performed.

The audit job uses a full-history checkout and scans all reachable Git refs with Gitleaks. The workflow grants only `contents: read`; every GitHub Action is pinned to a reviewed commit SHA, and the Gitleaks container is pinned by digest. The .env.example file is intentionally allowed.

Production SMTP delivery and production deployment remain untested. No production readiness or deployment claim is made. Sprint 2 remains planning-only and has not been implemented.
