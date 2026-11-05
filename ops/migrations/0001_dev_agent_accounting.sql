-- Versioned, INACTIVE control plane. Apply once on an isolated database only
-- after independent review. No role creation, grants to runners, or legacy
-- data conversion. Owner must be a restricted NOLOGIN role before activation.
BEGIN;
CREATE SCHEMA dev_agent_accounting;
REVOKE ALL ON SCHEMA dev_agent_accounting FROM PUBLIC;

CREATE TABLE dev_agent_accounting.project (
    project_id text PRIMARY KEY CHECK (project_id ~ '^proj_[A-Za-z0-9_-]{1,128}$'),
    enabled boolean NOT NULL DEFAULT false
);
CREATE TABLE dev_agent_accounting.cost_evidence (
    digest text PRIMARY KEY CHECK (digest ~ '^[a-f0-9]{64}$'),
    project_id text NOT NULL REFERENCES dev_agent_accounting.project,
    utc_day date NOT NULL,
    window_end timestamptz NOT NULL,
    observed_at timestamptz NOT NULL,
    reported_usd numeric(18,6) NOT NULL CHECK (reported_usd >= 0),
    producer_run bigint NOT NULL CHECK (producer_run > 0),
    producer_attempt integer NOT NULL CHECK (producer_attempt > 0),
    CHECK (window_end > utc_day::timestamp AT TIME ZONE 'UTC'),
    CHECK (window_end <= (utc_day + 1)::timestamp AT TIME ZONE 'UTC'),
    CHECK (observed_at >= window_end),
    UNIQUE (project_id, utc_day, window_end)
);
CREATE TABLE dev_agent_accounting.reservation (
    run_id bigint PRIMARY KEY CHECK (run_id > 0),
    issue_number bigint NOT NULL CHECK (issue_number > 0),
    head_sha text NOT NULL CHECK (head_sha ~ '^[a-f0-9]{40}$'),
    project_id text NOT NULL REFERENCES dev_agent_accounting.project,
    utc_day date NOT NULL,
    cost_digest text NOT NULL REFERENCES dev_agent_accounting.cost_evidence,
    reserved_usd numeric(18,6) NOT NULL DEFAULT 5 CHECK (reserved_usd = 5),
    state text NOT NULL DEFAULT 'reserved'
      CHECK (state IN ('reserved','started','failed_unreconciled','settled','cancelled_verified')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    ended_at timestamptz,
    CHECK ((state IN ('settled','cancelled_verified')) = (ended_at IS NOT NULL))
);
CREATE TABLE dev_agent_accounting.permit (
    nonce text PRIMARY KEY CHECK (nonce ~ '^[a-f0-9]{32,64}$'),
    run_id bigint NOT NULL UNIQUE REFERENCES dev_agent_accounting.reservation,
    consumed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE dev_agent_accounting.settlement (
    proof_digest text PRIMARY KEY CHECK (proof_digest ~ '^[a-f0-9]{64}$'),
    run_id bigint NOT NULL UNIQUE REFERENCES dev_agent_accounting.reservation,
    cost_digest text NOT NULL REFERENCES dev_agent_accounting.cost_evidence,
    decision text NOT NULL CHECK (decision IN ('settled','cancelled_verified')),
    review_reference text NOT NULL,
    finalized_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- Every mutation takes this same per-project lock FIRST. It serializes
-- ingestion, reservation, consumption and settlement, including across days.
CREATE FUNCTION dev_agent_accounting.ingest_cost(
    p_digest text, p_project text, p_day date, p_end timestamptz,
    p_observed timestamptz, p_amount numeric, p_run bigint, p_attempt integer
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE v_previous dev_agent_accounting.cost_evidence;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_project, 2601));
    IF NOT EXISTS (SELECT 1 FROM dev_agent_accounting.project
                   WHERE project_id=p_project AND enabled) THEN
        RAISE EXCEPTION 'project not enabled';
    END IF;
    IF p_observed > clock_timestamp() OR p_observed < clock_timestamp()-interval '5 minutes'
       OR p_amount <> trunc(p_amount,6) OR p_amount::text IN ('NaN','Infinity','-Infinity') THEN
        RAISE EXCEPTION 'invalid cost observation';
    END IF;
    IF EXISTS (SELECT 1 FROM dev_agent_accounting.cost_evidence WHERE digest=p_digest) THEN
        -- Digest is a verified canonical payload hash, not a caller-chosen ID.
        RETURN false;
    END IF;
    SELECT * INTO v_previous FROM dev_agent_accounting.cost_evidence
     WHERE project_id=p_project AND utc_day=p_day ORDER BY window_end DESC LIMIT 1;
    IF FOUND AND (p_end <= v_previous.window_end OR p_amount < v_previous.reported_usd) THEN
        RAISE EXCEPTION 'cost regression';
    END IF;
    INSERT INTO dev_agent_accounting.cost_evidence
      VALUES (p_digest,p_project,p_day,p_end,p_observed,p_amount,p_run,p_attempt);
    RETURN true;
END $$;

CREATE FUNCTION dev_agent_accounting.reserve_run(
    p_run bigint,p_issue bigint,p_sha text,p_project text,p_cost text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_cost dev_agent_accounting.cost_evidence;
    v_day date := (clock_timestamp() AT TIME ZONE 'UTC')::date;
    v_pending numeric;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_project, 2601));
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

CREATE FUNCTION dev_agent_accounting.consume_permit(
    p_nonce text,p_run bigint,p_issue bigint,p_sha text,p_project text,
    p_issued timestamptz,p_expires timestamptz
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_project,2601));
    IF p_issued IS NULL OR p_expires IS NULL OR p_issued>clock_timestamp()
       OR p_expires<=clock_timestamp() OR p_expires-p_issued>interval '5 minutes'
       OR p_expires<=p_issued THEN RETURN false; END IF;
    IF NOT EXISTS (SELECT 1 FROM dev_agent_accounting.project
                   WHERE project_id=p_project AND enabled) THEN RETURN false; END IF;
    PERFORM 1 FROM dev_agent_accounting.reservation
      WHERE run_id=p_run AND issue_number=p_issue AND head_sha=p_sha
        AND project_id=p_project AND state='reserved' FOR UPDATE;
    IF NOT FOUND THEN RETURN false; END IF;
    INSERT INTO dev_agent_accounting.permit(nonce,run_id) VALUES(p_nonce,p_run)
      ON CONFLICT DO NOTHING;
    IF NOT FOUND THEN RETURN false; END IF;
    UPDATE dev_agent_accounting.reservation SET state='started' WHERE run_id=p_run;
    RETURN true;
END $$;

CREATE FUNCTION dev_agent_accounting.finalize_run(
    p_proof text,p_run bigint,p_issue bigint,p_sha text,p_project text,
    p_decision text,p_cost text,p_finished timestamptz,p_reference text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE v_run dev_agent_accounting.reservation; v_cost dev_agent_accounting.cost_evidence;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_project,2601));
    SELECT * INTO v_run FROM dev_agent_accounting.reservation
      WHERE run_id=p_run AND issue_number=p_issue AND head_sha=p_sha
        AND project_id=p_project FOR UPDATE;
    IF NOT FOUND THEN RETURN false; END IF;
    IF v_run.state IN ('settled','cancelled_verified') THEN RETURN false; END IF;
    IF p_finished IS NULL OR p_finished<v_run.created_at OR p_finished>clock_timestamp()
       OR p_reference IS NULL OR length(p_reference)<1 OR length(p_reference)>200 THEN RETURN false; END IF;
    SELECT * INTO v_cost FROM dev_agent_accounting.cost_evidence
     WHERE digest=p_cost AND project_id=p_project AND utc_day=v_run.utc_day;
    IF NOT FOUND THEN RETURN false; END IF;
    IF p_decision='cancelled_verified' THEN
        -- Cancellation is valid only before a permit has ever been consumed.
        IF v_run.state<>'reserved' OR EXISTS (SELECT 1 FROM dev_agent_accounting.permit
              WHERE run_id=p_run) THEN RETURN false; END IF;
    ELSIF p_decision='settled' THEN
        IF v_run.state NOT IN ('started','failed_unreconciled')
           OR NOT EXISTS (SELECT 1 FROM dev_agent_accounting.permit WHERE run_id=p_run)
           OR v_cost.observed_at<p_finished+interval '24 hours'
           OR v_cost.window_end<least(p_finished,(v_run.utc_day+1)::timestamp AT TIME ZONE 'UTC')
           THEN RETURN false; END IF;
        -- 24h is a minimum review buffer, NOT proof of billing finality.
        -- An independently signed human-reviewed finality proof is mandatory
        -- in the protected service before invoking this function.
    ELSE RETURN false;
    END IF;
    INSERT INTO dev_agent_accounting.settlement
      (proof_digest,run_id,cost_digest,decision,review_reference)
      VALUES(p_proof,p_run,p_cost,p_decision,p_reference);
    UPDATE dev_agent_accounting.reservation SET state=p_decision,ended_at=p_finished WHERE run_id=p_run;
    RETURN true;
END $$;

CREATE FUNCTION dev_agent_accounting.mark_failed(p_run bigint,p_project text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_project,2601));
    UPDATE dev_agent_accounting.reservation SET state='failed_unreconciled'
     WHERE run_id=p_run AND project_id=p_project AND state='started';
    RETURN FOUND;
END $$;

REVOKE ALL ON ALL TABLES IN SCHEMA dev_agent_accounting FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA dev_agent_accounting FROM PUBLIC;
COMMIT;
