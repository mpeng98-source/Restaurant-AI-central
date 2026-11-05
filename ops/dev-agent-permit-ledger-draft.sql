-- REVIEW ONLY: apply to isolated Neon only after DBA approval and backup.
-- No permissions granted to dev_agent_runner, Codex, or restaurant roles.
CREATE TABLE IF NOT EXISTS dev_agent_control.consumed_permit (
  nonce text PRIMARY KEY
    CHECK (nonce ~ '^[a-f0-9]{32,64}$'),
  run_id bigint NOT NULL CHECK (run_id > 0),
  issue_number bigint NOT NULL CHECK (issue_number > 0),
  head_sha text NOT NULL CHECK (head_sha ~ '^[a-f0-9]{40}$'),
  project_id text NOT NULL CHECK (project_id ~ '^proj_[A-Za-z0-9_-]{1,128}$'),
  consumed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, issue_number, head_sha, project_id),
  UNIQUE (run_id)
);
-- Existing tables created from the previous draft require a separate
-- audited ALTER migration; CREATE TABLE IF NOT EXISTS does not upgrade them.
-- No verifier credentials or role creation are embedded in this draft.
