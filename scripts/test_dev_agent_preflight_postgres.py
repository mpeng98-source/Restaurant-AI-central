"""End-to-end preflight acceptance against ephemeral PostgreSQL 16.

No organization admin key or production database. Explicitly test allow,
duplicate, stale cost, and missing control-plane credential.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

import psycopg

URL = os.environ.get("DEV_AGENT_TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(URL, "ephemeral PostgreSQL URL required")
class PreflightDatabaseAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(URL, autocommit=True) as db:
            db.execute("DROP SCHEMA IF EXISTS dev_agent_control CASCADE")
            db.execute((ROOT / "ops/dev-agent-control-schema.sql").read_text())

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(URL, autocommit=True) as db:
            db.execute("DROP SCHEMA IF EXISTS dev_agent_control CASCADE")

    def setUp(self):
        with psycopg.connect(URL) as db:
            db.execute("TRUNCATE dev_agent_control.run_usage, dev_agent_control.run_reservation, dev_agent_control.alert_outbox, dev_agent_control.cost_observation, dev_agent_control.daily_budget CASCADE")

    def invoke(self, run_id, env_url=URL):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "permit.json"
            env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts")}
            if env_url:
                env["DEV_AGENT_CONTROL_DATABASE_URL"] = env_url
            else:
                env.pop("DEV_AGENT_CONTROL_DATABASE_URL", None)
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts/dev_agent_preflight.py"),
                 "--run-id", str(run_id), "--issue", "987",
                 "--project-id", "proj_agent", "--output", str(output)],
                env=env, capture_output=True, text=True, timeout=15)
            return proc.returncode, output.exists()

    def seed(self, observed):
        with psycopg.connect(URL) as db:
            db.execute("""
                INSERT INTO dev_agent_control.daily_budget
                (project_id, utc_day, max_runs, daily_budget_usd, cost_observed_at)
                VALUES ('proj_agent', %s, 6, 10, %s)
            """, (datetime.now(timezone.utc).date(), observed))

    def test_fresh_evidence_allows_once_and_duplicate_denied(self):
        self.seed(datetime.now(timezone.utc))
        self.assertEqual(self.invoke(93001), (0, True))
        self.assertEqual(self.invoke(93001), (2, False))

    def test_stale_cost_evidence_denies(self):
        self.seed(datetime.now(timezone.utc) - timedelta(hours=2))
        self.assertEqual(self.invoke(93002), (2, False))

    def test_missing_secret_denies(self):
        self.assertEqual(self.invoke(93003, env_url=None), (2, False))

    def test_missing_cost_evidence_denies(self):
        self.assertEqual(self.invoke(93004), (2, False))


if __name__ == "__main__":
    unittest.main()
