-- DBA REVIEW ONLY. Run with schema owner privileges in isolated Neon.
-- This creates a NOLOGIN group and a restricted LOGIN role with no password.
-- Provision its random password out-of-band using Neon, never in this file.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='dev_agent_permit_verifier') THEN
    CREATE ROLE dev_agent_permit_verifier NOLOGIN
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END $$;
-- A login role must be provisioned separately and granted membership
-- only after the security-definer function has passed independent audit.
REVOKE ALL ON dev_agent_control.consumed_permit FROM PUBLIC;
REVOKE ALL ON dev_agent_control.consumed_permit FROM dev_agent_runner;
-- The verifier must not have direct INSERT/UPDATE/DELETE on the ledger.
-- A later audited SECURITY DEFINER function will grant EXECUTE only.
