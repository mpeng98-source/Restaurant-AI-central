-- Review-only migration for the isolated Dev Agent control database.
-- Do NOT apply to Neon until independently approved and backup verified.
ALTER TABLE dev_agent_control.run_reservation
  DROP CONSTRAINT IF EXISTS run_reservation_state_check;
ALTER TABLE dev_agent_control.run_reservation
  ADD CONSTRAINT run_reservation_state_check
  CHECK (state IN ('reserved','started','failed_unreconciled','settled','cancelled_verified'));
ALTER TABLE dev_agent_control.run_reservation
  ADD COLUMN IF NOT EXISTS settled_at timestamptz,
  ADD COLUMN IF NOT EXISTS settlement_proof text,
  ADD COLUMN IF NOT EXISTS settled_amount_usd numeric(18,6)
    CHECK (settled_amount_usd IS NULL OR settled_amount_usd >= 0);
CREATE INDEX IF NOT EXISTS idx_dev_agent_reservations_project_day
  ON dev_agent_control.run_reservation (project_id, utc_day, state);
-- Granting table-wide UPDATE to a runner is NOT sufficient least privilege.
-- Use separately audited SECURITY DEFINER functions or a dedicated settlement role.
