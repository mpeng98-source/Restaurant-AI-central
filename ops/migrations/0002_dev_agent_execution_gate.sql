-- Apply AFTER 0001 on the isolated Dev Agent control database. No grants.
BEGIN;
ALTER TABLE dev_agent_accounting.reservation
  ADD COLUMN run_attempt integer CHECK (run_attempt > 0),
  ADD COLUMN task_digest text CHECK (task_digest ~ '^[a-f0-9]{64}$');
CREATE UNIQUE INDEX one_pending_task_per_project
  ON dev_agent_accounting.reservation(project_id,issue_number)
  WHERE state IN ('reserved','started','failed_unreconciled');

CREATE FUNCTION dev_agent_accounting.reserve_task(
  p_run bigint,p_attempt integer,p_issue bigint,p_sha text,p_project text,p_cost text,p_task text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF p_attempt IS NULL OR p_attempt<1 OR p_task IS NULL OR p_task !~ '^[a-f0-9]{64}$'
    THEN RETURN false; END IF;
  IF NOT dev_agent_accounting.reserve_run(p_run,p_issue,p_sha,p_project,p_cost)
    THEN RETURN false; END IF;
  UPDATE dev_agent_accounting.reservation SET run_attempt=p_attempt,task_digest=p_task WHERE run_id=p_run;
  RETURN true;
END $$;

CREATE FUNCTION dev_agent_accounting.authorize_task(
  p_nonce text,p_run bigint,p_attempt integer,p_issue bigint,p_sha text,p_project text,
  p_task text,p_issued timestamptz,p_expires timestamptz
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(p_project,2601));
  PERFORM 1 FROM dev_agent_accounting.reservation
   WHERE run_id=p_run AND run_attempt=p_attempt AND issue_number=p_issue
     AND head_sha=p_sha AND project_id=p_project AND task_digest=p_task AND state='reserved'
   FOR UPDATE;
  IF NOT FOUND THEN RETURN false; END IF;
  RETURN dev_agent_accounting.consume_permit(p_nonce,p_run,p_issue,p_sha,p_project,p_issued,p_expires);
END $$;

-- Only counts, never credentials or raw operational rows, are exposed.
-- The restricted function owner needs SELECT on the legacy reservation table.
-- Missing permission/unknown legacy state fails closed; never hide exceptions.
CREATE FUNCTION dev_agent_accounting.rollout_status(p_project text)
RETURNS TABLE(project_enabled boolean,legacy_pending bigint,legacy_today bigint,unbound_pending bigint)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  project_enabled := coalesce((SELECT enabled FROM dev_agent_accounting.project WHERE project_id=p_project),false);
  legacy_pending := 0; legacy_today := 0;
  IF to_regclass('dev_agent_control.run_reservation') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FILTER (WHERE state NOT IN (''settled'',''cancelled_verified'')),
                    count(*) FILTER (WHERE utc_day=(now() AT TIME ZONE ''UTC'')::date)
               FROM dev_agent_control.run_reservation' INTO legacy_pending,legacy_today;
  END IF;
  SELECT count(*) INTO unbound_pending FROM dev_agent_accounting.reservation
   WHERE project_id=p_project AND state IN ('reserved','started','failed_unreconciled')
     AND (run_attempt IS NULL OR task_digest IS NULL);
  RETURN NEXT;
END $$;
REVOKE ALL ON FUNCTION dev_agent_accounting.reserve_task(bigint,integer,bigint,text,text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION dev_agent_accounting.authorize_task(text,bigint,integer,bigint,text,text,text,timestamptz,timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION dev_agent_accounting.rollout_status(text) FROM PUBLIC;
COMMIT;
