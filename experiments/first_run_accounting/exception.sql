-- REVIEW CANDIDATE ONLY. Never run as part of worker startup.
-- Requires explicit approval for this schema and exact-run policy installation.
-- No login creation, grants, policy INSERT, or enable operation is included.
BEGIN;
CREATE SCHEMA dev_agent_canary_exception AUTHORIZATION dev_agent_accounting_owner_v27;
REVOKE ALL ON SCHEMA dev_agent_canary_exception FROM PUBLIC;
CREATE TABLE dev_agent_canary_exception.policy (
  singleton boolean PRIMARY KEY CHECK(singleton),
  project text NOT NULL CHECK(project='proj_Nkd1G85QX72VHwdQ8mEg8CRa'),
  issue bigint NOT NULL CHECK(issue=58),
  run_id bigint NOT NULL CHECK(run_id>0),
  attempt integer NOT NULL CHECK(attempt=1),
  head text NOT NULL CHECK(head ~ '^[a-f0-9]{40}$'),
  task_digest text NOT NULL CHECK(task_digest ~ '^[a-f0-9]{64}$'),
  request_digest text NOT NULL CHECK(request_digest ~ '^[a-f0-9]{64}$'),
  approval_digest text NOT NULL CHECK(approval_digest ~ '^[a-f0-9]{64}$'),
  valid_from timestamptz NOT NULL,
  valid_until timestamptz NOT NULL,
  request_ceiling_usd numeric(18,6) NOT NULL CHECK(request_ceiling_usd=5),
  prior_cost_state text NOT NULL CHECK(prior_cost_state='unknown'),
  CHECK(valid_until>valid_from AND valid_until-valid_from<=interval '1 hour'),
  CHECK((valid_from AT TIME ZONE 'America/Los_Angeles')::date =
        ((valid_until-interval '1 microsecond') AT TIME ZONE 'America/Los_Angeles')::date)
);
CREATE TABLE dev_agent_canary_exception.claim (
  singleton boolean PRIMARY KEY REFERENCES dev_agent_canary_exception.policy(singleton),
  consumed_at timestamptz NOT NULL,
  outcome text NOT NULL CHECK(outcome='unknown_no_retry')
);
ALTER TABLE dev_agent_canary_exception.policy OWNER TO dev_agent_accounting_owner_v27;
ALTER TABLE dev_agent_canary_exception.claim OWNER TO dev_agent_accounting_owner_v27;
REVOKE ALL ON ALL TABLES IN SCHEMA dev_agent_canary_exception FROM PUBLIC;

CREATE FUNCTION dev_agent_canary_exception.consume(
  p_project text,p_issue bigint,p_run bigint,p_attempt integer,p_head text,
  p_task text,p_request text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  cfg dev_agent_canary_exception.policy%ROWTYPE;
  readiness record;
BEGIN
  -- A transaction-wide snapshot can miss a competitor even after lock acquisition.
  IF current_setting('transaction_isolation') <> 'read committed' THEN RETURN false; END IF;
  -- Same project lock as ordinary accounting; never race another reservation.
  PERFORM pg_advisory_xact_lock(hashtextextended(p_project,2601));
  SELECT * INTO cfg FROM dev_agent_canary_exception.policy WHERE singleton FOR UPDATE;
  IF NOT FOUND THEN RETURN false; END IF;
  IF ROW(p_project,p_issue,p_run,p_attempt,p_head,p_task,p_request)
     IS DISTINCT FROM ROW(cfg.project,cfg.issue,cfg.run_id,cfg.attempt,cfg.head,cfg.task_digest,cfg.request_digest)
     OR clock_timestamp()<cfg.valid_from OR clock_timestamp()>=cfg.valid_until
     THEN RETURN false; END IF;
  SELECT * INTO readiness FROM dev_agent_accounting.rollout_status(p_project);
  IF readiness.project_enabled IS DISTINCT FROM true OR readiness.legacy_pending<>0
     OR readiness.legacy_today<>0 OR readiness.unbound_pending<>0 THEN RETURN false; END IF;
  -- A bootstrap exception never races any normal unresolved request.
  IF EXISTS(SELECT 1 FROM dev_agent_accounting.reservation WHERE project_id=p_project
            AND state IN ('reserved','started','failed_unreconciled')) THEN RETURN false; END IF;
  INSERT INTO dev_agent_canary_exception.claim VALUES(true,clock_timestamp(),'unknown_no_retry')
    ON CONFLICT DO NOTHING;
  RETURN FOUND;
END $$;
ALTER FUNCTION dev_agent_canary_exception.consume(text,bigint,bigint,integer,text,text,text)
 OWNER TO dev_agent_accounting_owner_v27;
REVOKE ALL ON FUNCTION dev_agent_canary_exception.consume(text,bigint,bigint,integer,text,text,text) FROM PUBLIC;

-- Preserve the original signature, owner and grants; only add the locked guard.
CREATE OR REPLACE FUNCTION dev_agent_accounting.reserve_run(
    p_run bigint,p_issue bigint,p_sha text,p_project text,p_cost text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_cost dev_agent_accounting.cost_evidence;
    v_day date := (clock_timestamp() AT TIME ZONE 'UTC')::date;
    v_pending numeric;
BEGIN
    -- Only READ COMMITTED refreshes subsequent queries after the advisory wait.
    IF current_setting('transaction_isolation') <> 'read committed' THEN RETURN false; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(p_project, 2601));
    -- A consumed exception blocks every subsequent ordinary reservation until
    -- separately reviewed reconciliation. Do not silently lose unknown exposure.
    IF EXISTS (SELECT 1 FROM dev_agent_canary_exception.claim c
               JOIN dev_agent_canary_exception.policy p USING (singleton)
               WHERE p.project=p_project) THEN RETURN false; END IF;
    IF NOT EXISTS (SELECT 1 FROM dev_agent_accounting.project
                   WHERE project_id=p_project AND enabled) THEN RETURN false; END IF;
    IF EXISTS (SELECT 1 FROM dev_agent_accounting.reservation WHERE run_id=p_run) THEN RETURN false; END IF;
    SELECT * INTO v_cost FROM dev_agent_accounting.cost_evidence
     WHERE digest=p_cost AND project_id=p_project AND utc_day=v_day;
    IF NOT FOUND OR v_cost.observed_at < clock_timestamp()-interval '1 hour'
       OR v_cost.window_end < clock_timestamp()-interval '1 hour'
       OR EXISTS (SELECT 1 FROM dev_agent_accounting.cost_evidence
          WHERE project_id=p_project AND utc_day=v_day AND window_end>v_cost.window_end)
       THEN RETURN false; END IF;
    IF (SELECT count(*) FROM dev_agent_accounting.reservation
         WHERE project_id=p_project AND utc_day=v_day) >= 6 THEN RETURN false; END IF;
    -- An unresolved previous-day run must never disappear at UTC rollover.
    SELECT coalesce(sum(reserved_usd),0) INTO v_pending
      FROM dev_agent_accounting.reservation WHERE project_id=p_project
       AND state IN ('reserved','started','failed_unreconciled');
    IF v_cost.reported_usd+v_pending+5>10 THEN RETURN false; END IF;
    INSERT INTO dev_agent_accounting.reservation
      (run_id,issue_number,head_sha,project_id,utc_day,cost_digest)
      VALUES (p_run,p_issue,p_sha,p_project,v_day,p_cost);
    RETURN true;
END $$;

COMMIT;
