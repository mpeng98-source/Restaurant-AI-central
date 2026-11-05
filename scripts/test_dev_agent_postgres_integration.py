"""Real PostgreSQL transaction/concurrency acceptance tests; no mocks.

Run only against an ephemeral isolated test database with superuser schema setup.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import unittest
import psycopg
from dev_agent_durable_controls import reserve

URL = os.environ.get("DEV_AGENT_TEST_DATABASE_URL")
SCHEMA = Path(__file__).resolve().parents[1] / "ops" / "dev-agent-control-schema.sql"


@unittest.skipUnless(URL, "DEV_AGENT_TEST_DATABASE_URL required")
class PostgresConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(URL, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP SCHEMA IF EXISTS dev_agent_control CASCADE")
                cur.execute(SCHEMA.read_text())

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(URL, autocommit=True) as conn:
            conn.execute("DROP SCHEMA IF EXISTS dev_agent_control CASCADE")

    def setUp(self):
        self.now = datetime.now(timezone.utc)
        with psycopg.connect(URL) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM dev_agent_control.run_usage")
                cur.execute("DELETE FROM dev_agent_control.run_reservation")
                cur.execute("DELETE FROM dev_agent_control.alert_outbox")
                cur.execute("DELETE FROM dev_agent_control.daily_budget")
                cur.execute("""
                    INSERT INTO dev_agent_control.daily_budget
                    (project_id, utc_day, max_runs, daily_budget_usd, reported_usd, cost_observed_at)
                    VALUES ('proj_agent', %s, 6, 10, 0, %s)
                """, (self.now.date(), self.now))

    def test_two_reservations_only_and_concurrent_third_blocked(self):
        def attempt(n):
            with psycopg.connect(URL) as conn:
                return reserve(conn, run_id=1000+n, issue_number=2000+n,
                               project_id="proj_agent", now=self.now)
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(attempt, range(5)))
        self.assertEqual(sum(r["allowed"] for r in results), 2)
        with psycopg.connect(URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*), sum(reserved_usd) FROM dev_agent_control.run_reservation")
                self.assertEqual(cur.fetchone(), (2, 10))

    def test_retry_same_run_does_not_charge_twice(self):
        with psycopg.connect(URL) as conn:
            first = reserve(conn, run_id=1234, issue_number=4321, project_id="proj_agent", now=self.now)
        with psycopg.connect(URL) as conn:
            second = reserve(conn, run_id=1234, issue_number=4321, project_id="proj_agent", now=self.now)
        self.assertTrue(first["allowed"])
        self.assertFalse(second["allowed"])

    def test_same_issue_competing_runs_unique(self):
        def attempt(n):
            with psycopg.connect(URL) as conn:
                try:
                    return reserve(conn, run_id=2000+n, issue_number=777,
                                   project_id="proj_agent", now=self.now)["allowed"]
                except psycopg.errors.UniqueViolation:
                    return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertEqual(sum(results), 1)


if __name__ == "__main__":
    unittest.main()
