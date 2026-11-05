# Chubby AI platform foundation

## Scope

Sprint 1 implements invite-only identity, server-side sessions, role and location authorization, PostgreSQL row security, an authenticated web entry flow, and CI/runtime verification. Inventory and Sprint 2 work are out of scope.

## Toolchain

- Python 3.12 (locked dependencies in `backend/requirements.lock`)
- Node.js 24.22.2 and pnpm 11.25.0 (`.nvmrc`, package manager pin, and `frontend/pnpm-lock.yaml`)
- Docker Engine/Desktop with Compose, PostgreSQL 16, and Redis 7 for the full stack

`backend/requirements.txt` lists direct packages; `requirements.lock` pins the full Python resolution. Install only from locks for repeatable setup. On macOS with Homebrew, install host runtimes with `brew install python@3.12 node@24` and Docker Desktop with `brew install --cask docker`. Otherwise use the official Python, Node.js, and Docker installers.

### Preinstalled development toolchain

Open this repository in a GitHub Codespace or use **Dev Containers: Reopen in Container** in VS Code. The development image installs the exact Node.js version from `.nvmrc` and pnpm version from `frontend/package.json` once during image creation, verifies the Node archive checksum, and includes Python 3.12. Only toolchain manifests enter its Docker build context. Container creation installs the frozen frontend dependency lock; subsequent checks use `pnpm` directly, without `npm exec` downloads.

```sh
node --version
pnpm --version
pnpm --dir frontend run typecheck
pnpm --dir frontend run lint
pnpm --dir frontend run build
```

Change `.nvmrc` or `frontend/package.json` only as part of a reviewed toolchain upgrade, then rebuild the container; the image reads these pins rather than maintaining another version copy. Docker/Compose access and application/database credentials are not provisioned by this development container. Full-stack checks still require the separate local setup below.

## Local setup

```sh
cp .env.example .env
# Generate independent secrets with `openssl rand -hex 32` for POSTGRES_PASSWORD, APP_DATABASE_PASSWORD, MIGRATION_DATABASE_PASSWORD, and SESSION_SECRET. Set DATABASE_URL and MIGRATION_DATABASE_URL to use their matching database passwords. Compose fails closed when any required value is missing.
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
cd frontend && corepack pnpm install --frozen-lockfile && cd ..
docker compose up --build
```

The web app is at <http://localhost:3000>; the API docs are at <http://localhost:8000/docs>. After Compose starts, run `cd frontend && corepack pnpm run test:smoke` for the basic HTTP interface check. `/health` is liveness and `/ready` checks PostgreSQL, Redis, and that the API is using the restricted `chubby_app` role. Compose starts PostgreSQL and Redis, runs migrations once as `chubby_migrator`, then starts the API, worker, and web app. PostgreSQL initialization creates separate `chubby_migrator` and `chubby_app` accounts. The API and worker never receive the migration credentials.

To create the first corporate owner after the migration has completed, run this one-time command from the repository root with environment values loaded from the protected local environment:

```sh
set -a && . ./.env && set +a
BOOTSTRAP_OWNER_EMAIL='owner@your-company.example' BOOTSTRAP_OWNER_PASSWORD='<strong generated password>' \
  PYTHONPATH=backend DATABASE_URL="$DATABASE_URL" .venv/bin/python -m app.bootstrap_owner
```

The command creates no default credentials and refuses to replace an existing user. Remove the bootstrap password from the shell/process environment when finished. In production, supply the bootstrap values through the managed secrets mechanism and run it once from a controlled task.

Set SMTP values in `.env` for invitation and password-reset email delivery outside development/test. Production configuration requires SMTP host/from address, HTTPS origins, `COOKIE_SECURE=true`, and a unique `SESSION_SECRET` of at least 32 bytes. Do not commit `.env` or real credentials.

## Verification

Run backend checks:

```sh
.venv/bin/python -c 'import fastapi, sqlalchemy, alembic, psycopg, app.models'
.venv/bin/python -m alembic -c backend/alembic.ini history
.venv/bin/python -m pytest -c backend/pyproject.toml -q
```

Run frontend checks:

```sh
cd frontend
corepack pnpm install --frozen-lockfile
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm run build
corepack pnpm run test:smoke
```

After Compose is healthy, run the mandatory PostgreSQL integration suite from the root with the restricted app connection and the separate migration/test fixture credentials configured:

```sh
set -a && . ./.env && set +a
TEST_DATABASE_URL="postgresql+psycopg://chubby_app:${APP_DATABASE_PASSWORD}@localhost:5432/chubby" \
TEST_MIGRATION_DATABASE_URL="postgresql+psycopg://chubby_migrator:${MIGRATION_DATABASE_PASSWORD}@localhost:5432/chubby" \
TEST_FIXTURE_DATABASE_URL="postgresql+psycopg://postgres:${POSTGRES_PASSWORD}@localhost:5432/chubby" \
.venv/bin/python -m pytest -c backend/pyproject.toml -m postgres -q
```

`TEST_FIXTURE_DATABASE_URL` is only for creating isolated test fixtures. All API and direct RLS assertions use `TEST_DATABASE_URL` as `chubby_app`; migrations and the owner-level append-only trigger test use `chubby_migrator`. CI fails before pytest if any required test database URL is missing. PostgreSQL tests must never be replaced with SQLite or mocked databases.

The GitHub Actions workflow `.github/workflows/sprint-1b.yml` runs the backend/security suite against PostgreSQL and Redis, frontend checks, Docker Compose validation, then starts the full Compose stack and checks readiness and shutdown. All third-party Actions are pinned to reviewed commit SHAs.

## Deployment status

No staging deployment is represented by this repository. Read [operations](docs/operations.md) before setting up an isolated staging environment. Sprint 1 acceptance requires the mandatory PostgreSQL and Compose jobs to pass; local unit checks alone are not sufficient.

To run the hosted verification, push this repository to GitHub with Actions enabled, then open **Actions → Sprint 1B security and runtime verification → Run workflow** (or push a pull request/main update). Wait for both `verify` and `compose-runtime` jobs to pass. The workflow uses GitHub-hosted Ubuntu and runs the real PostgreSQL suite; a green local frontend build is not a substitute. This workspace currently has no Git remote or commit, so it cannot trigger or report a hosted run from here.

## Connect this workspace to GitHub

The initial source set is staged in the local Git index. No remote is configured. To connect it without overwriting or guessing a repository:

1. In GitHub, create or select the intended **private** repository. For a new repository, leave README, license, and `.gitignore` initialization unchecked so the first push has no unrelated history.
2. Set the commit identity to the name and verified email you want on GitHub (GitHub's verified noreply address is fine):

   ```sh
   git config --local user.name "Your Name"
   git config --local user.email "your-verified-github-email"
   ```

3. Copy the exact HTTPS or SSH URL from that repository. Confirm `git remote -v` is still empty, then add that actual URL:

   ```sh
   git remote -v
   git remote add origin <URL-copied-from-GitHub>
   git status --short
   git diff --cached --check
   git commit -m "Initial Chubby AI Sprint 1B implementation"
   git push -u origin main
   ```

   Do not run `git remote add` if a remote already exists; inspect and confirm it first. Do not push until the staged-file list and commit identity are correct.

4. In GitHub, open **Actions → Sprint 1B security and runtime verification → Run workflow**. Wait for both `verify` and `compose-runtime` jobs. The workflow is also triggered by a pull request or push to `main`. Require both jobs to pass before accepting Sprint 1.
