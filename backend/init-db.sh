#!/bin/sh
set -eu
: "${APP_DATABASE_PASSWORD:?APP_DATABASE_PASSWORD must be set}"
: "${MIGRATION_DATABASE_PASSWORD:?MIGRATION_DATABASE_PASSWORD must be set}"
: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${POSTGRES_DB:?POSTGRES_DB must be set}"
[ "$POSTGRES_DB" = "chubby" ] || { printf '%s\n' 'POSTGRES_DB must be chubby' >&2; exit 1; }
# Do not place passwords in psql arguments or echo SQL to stdout.
psql --no-psqlrc --quiet --set=ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\set QUIET 1
\getenv app_password APP_DATABASE_PASSWORD
\getenv migration_password MIGRATION_DATABASE_PASSWORD
-- Keep role DDL out of PostgreSQL statement and error logs for this session.
SET log_statement = 'none';
SET log_min_error_statement = 'panic';
SET log_min_duration_statement = -1;
SET log_duration = off;
SET log_min_duration_sample = -1;
SET log_transaction_sample_rate = 0;
SET log_parameter_max_length = 0;
SET log_parameter_max_length_on_error = 0;
CREATE ROLE chubby_migrator LOGIN PASSWORD :'migration_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE chubby_app LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT CONNECT ON DATABASE chubby TO chubby_migrator, chubby_app;
ALTER SCHEMA public OWNER TO chubby_migrator;
GRANT USAGE ON SCHEMA public TO chubby_app;
ALTER DEFAULT PRIVILEGES FOR ROLE chubby_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO chubby_app;
ALTER DEFAULT PRIVILEGES FOR ROLE chubby_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO chubby_app;
SQL
