-- Standalone Dev Agent control-plane schema, not an inventory migration.
-- Apply manually using a dedicated restricted role after DBA review.
CREATE SCHEMA IF NOT EXISTS dev_agent_control;
CREATE TABLE IF NOT EXISTS dev_agent_control.daily_budget (
    project_id text NOT NULL,
    utc_day date NOT NULL,
    max_runs integer NOT NULL CHECK (max_runs = 6),
    daily_budget_usd numeric(18,6) NOT NULL CHECK (daily_budget_usd = 10),
    reserved_usd numeric(18,6) NOT NULL DEFAULT 0 CHECK (reserved_usd >= 0),
    reported_usd numeric(18,6) NOT NULL DEFAULT 0 CHECK (reported_usd >= 0),
    cost_observed_at timestamptz,
    PRIMARY KEY (project_id, utc_day)
);
CREATE TABLE IF NOT EXISTS dev_agent_control.run_reservation (
    run_id bigint PRIMARY KEY CHECK (run_id > 0),
    project_id text NOT NULL,
    utc_day date NOT NULL,
    issue_number bigint NOT NULL CHECK (issue_number > 0),
    reserved_usd numeric(18,6) NOT NULL CHECK (reserved_usd = 5),
    state text NOT NULL DEFAULT 'reserved'
        CHECK (state IN ('reserved', 'started', 'completed', 'failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, utc_day, issue_number),
    FOREIGN KEY (project_id, utc_day)
      REFERENCES dev_agent_control.daily_budget(project_id, utc_day)
);
CREATE TABLE IF NOT EXISTS dev_agent_control.alert_outbox (
    alert_key text PRIMARY KEY,
    run_id bigint,
    alert_code text NOT NULL,
    state text NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'sending', 'sent')),
    created_at timestamptz NOT NULL DEFAULT now(),
    delivered_at timestamptz,
    github_issue_number bigint
);
-- Do not grant table access to Codex, public, or the restaurant API role.
