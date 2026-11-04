-- REVIEW-ONLY. Apply only after independent DBA/security approval.
-- Execute as the dedicated control-schema owner, NEVER dev_agent_runner.
-- Requires consumed_permit table with UNIQUE(run_id) and strict CHECK constraints.
-- The caller MUST verify the signed envelope and expiry outside SQL first.
-- This function enforces reservation binding and atomic one-time consumption,
-- but does not cryptographically validate the signature itself.
CREATE OR REPLACE FUNCTION dev_agent_control.consume_verified_permit(
    p_nonce text, p_run_id bigint, p_issue bigint, p_sha text, p_project text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_inserted text;
BEGIN
    IF p_nonce !~ '^[a-f0-9]{32,64}$'
       OR p_sha !~ '^[a-f0-9]{40}$'
       OR p_project !~ '^proj_[A-Za-z0-9_-]{1,128}$'
       OR p_run_id <= 0 OR p_issue <= 0 THEN
        RAISE EXCEPTION 'invalid permit binding';
    END IF;
    -- Reservation row is locked to prevent a concurrent state transition.
    PERFORM 1 FROM dev_agent_control.run_reservation
     WHERE run_id = p_run_id AND issue_number = p_issue
       AND project_id = p_project AND state = 'reserved'
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    INSERT INTO dev_agent_control.consumed_permit
        (nonce, run_id, issue_number, head_sha, project_id)
    VALUES (p_nonce, p_run_id, p_issue, p_sha, p_project)
    ON CONFLICT DO NOTHING
    RETURNING nonce INTO v_inserted;
    RETURN v_inserted IS NOT NULL;
END;
$$;
REVOKE ALL ON FUNCTION dev_agent_control.consume_verified_permit(text,bigint,bigint,text,text) FROM PUBLIC;
-- No direct grant to dev_agent_runner; review existing grants before deployment.
-- Do not GRANT EXECUTE until a dedicated login and protected workflow are reviewed.
-- SECURITY DEFINER ownership, schema permissions and caller identity require DBA verification.
