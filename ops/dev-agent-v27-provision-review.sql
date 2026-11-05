-- REVIEWED APPLICATION PLAN ONLY; no passwords or project enablement.
-- Run after migrations 0001 + 0002, only on the isolated control database.
-- Existing identity/grants are never silently repaired: the readiness audit
-- must pass before any activation. Provision passwords in a protected channel.
DO $$
DECLARE name text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='dev_agent_accounting_owner_v27') THEN
    CREATE ROLE dev_agent_accounting_owner_v27 NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
  FOREACH name IN ARRAY ARRAY['dev_agent_cost_writer_v27','dev_agent_reserver_v27',
      'dev_agent_verifier_v27','dev_agent_settler_v27','dev_agent_failure_v27','dev_agent_auditor_v27'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=name) THEN
      EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',name);
    END IF;
  END LOOP;
END $$;
GRANT dev_agent_accounting_owner_v27 TO CURRENT_USER;
-- Ownership transfer checks CREATE on the target schema/database even for a
-- restricted NOLOGIN owner. Grant before transfer; remove database CREATE below.
GRANT USAGE,CREATE ON SCHEMA dev_agent_accounting TO dev_agent_accounting_owner_v27;
DO $$ BEGIN
  EXECUTE format('GRANT CREATE ON DATABASE %I TO dev_agent_accounting_owner_v27',current_database());
END $$;
DO $$
DECLARE obj record;
BEGIN
  FOR obj IN SELECT c.oid::regclass AS name FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
              WHERE n.nspname='dev_agent_accounting' AND c.relkind='r' LOOP
    EXECUTE format('ALTER TABLE %s OWNER TO dev_agent_accounting_owner_v27',obj.name);
  END LOOP;
  FOR obj IN SELECT p.oid::regprocedure AS name FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
              WHERE n.nspname='dev_agent_accounting' LOOP
    EXECUTE format('ALTER FUNCTION %s OWNER TO dev_agent_accounting_owner_v27',obj.name);
  END LOOP;
  IF to_regclass('dev_agent_control.run_reservation') IS NOT NULL THEN
    GRANT USAGE ON SCHEMA dev_agent_control TO dev_agent_accounting_owner_v27;
    GRANT SELECT ON dev_agent_control.run_reservation TO dev_agent_accounting_owner_v27;
  END IF;
END $$;
ALTER SCHEMA dev_agent_accounting OWNER TO dev_agent_accounting_owner_v27;
DO $$ BEGIN
  EXECUTE format('REVOKE CREATE ON DATABASE %I FROM dev_agent_accounting_owner_v27',current_database());
END $$;
GRANT USAGE,CREATE ON SCHEMA dev_agent_accounting TO dev_agent_accounting_owner_v27;
GRANT ALL ON ALL TABLES IN SCHEMA dev_agent_accounting TO dev_agent_accounting_owner_v27;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA dev_agent_accounting TO dev_agent_accounting_owner_v27;
REVOKE ALL ON SCHEMA dev_agent_accounting FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA dev_agent_accounting FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA dev_agent_accounting FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE dev_agent_accounting_owner_v27 IN SCHEMA dev_agent_accounting
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
GRANT USAGE ON SCHEMA dev_agent_accounting TO dev_agent_cost_writer_v27,dev_agent_reserver_v27,
  dev_agent_verifier_v27,dev_agent_settler_v27,dev_agent_failure_v27,dev_agent_auditor_v27;
GRANT EXECUTE ON FUNCTION dev_agent_accounting.ingest_cost(text,text,date,timestamptz,timestamptz,numeric,bigint,integer) TO dev_agent_cost_writer_v27;
GRANT EXECUTE ON FUNCTION dev_agent_accounting.reserve_task(bigint,integer,bigint,text,text,text,text) TO dev_agent_reserver_v27;
GRANT EXECUTE ON FUNCTION dev_agent_accounting.authorize_task(text,bigint,integer,bigint,text,text,text,timestamptz,timestamptz) TO dev_agent_verifier_v27;
GRANT EXECUTE ON FUNCTION dev_agent_accounting.finalize_run(text,bigint,bigint,text,text,text,text,timestamptz,text) TO dev_agent_settler_v27;
GRANT EXECUTE ON FUNCTION dev_agent_accounting.mark_failed(bigint,text) TO dev_agent_failure_v27;
GRANT EXECUTE ON FUNCTION dev_agent_accounting.rollout_status(text) TO dev_agent_auditor_v27;
-- No project is inserted/enabled and no activation variable is set here.
