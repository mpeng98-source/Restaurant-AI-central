-- REVIEW ONLY. Apply to isolated Neon after DBA approval.
CREATE TABLE IF NOT EXISTS dev_agent_control.consumed_permit (
  nonce text PRIMARY KEY CHECK (length(nonce) BETWEEN 32 AND 64),
  run_id bigint NOT NULL,
  issue_number bigint NOT NULL,
  head_sha text NOT NULL CHECK (length(head_sha)=40),
  project_id text NOT NULL,
  consumed_at timestamptz NOT NULL DEFAULT now()
);
-- Dedicated verifier role only. Do not grant to Codex or restaurant API roles.
