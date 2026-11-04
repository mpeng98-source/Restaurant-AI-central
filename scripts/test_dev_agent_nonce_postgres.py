"""Real PostgreSQL single-use nonce acceptance.

Only run against ephemeral CI PostgreSQL. Never drop a schema on Neon.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest
import psycopg
from dev_agent_permit_ledger import consume_nonce

URL = os.environ.get("DEV_AGENT_TEST_DATABASE_URL")
DDL = Path(__file__).resolve().parents[1] / "ops/dev-agent-permit-ledger-draft.sql"


@unittest.skipUnless(URL, "ephemeral PostgreSQL URL required")
class NoncePostgresAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(URL, autocommit=True) as db:
            db.execute("CREATE SCHEMA IF NOT EXISTS dev_agent_control")
            db.execute(DDL.read_text())

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(URL, autocommit=True) as db:
            db.execute("DROP TABLE IF EXISTS dev_agent_control.consumed_permit")

    def setUp(self):
        with psycopg.connect(URL) as db:
            db.execute("DELETE FROM dev_agent_control.consumed_permit")

    def consume(self, nonce, run_id=123):
        with psycopg.connect(URL) as db:
            return consume_nonce(db, nonce=nonce, run_id=run_id, issue_number=39,
                                 head_sha="a"*40, project_id="proj_agent")

    def test_same_nonce_parallel_only_one_wins(self):
        nonce = "b"*32
        with ThreadPoolExecutor(max_workers=12) as pool:
            outcomes = list(pool.map(lambda _: self.consume(nonce), range(12)))
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(outcomes.count(False), 11)
        with psycopg.connect(URL) as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM dev_agent_control.consumed_permit WHERE nonce=%s",
                (nonce,)).fetchone()[0], 1)

    def test_replay_after_commit_is_denied(self):
        self.assertTrue(self.consume("c"*32))
        self.assertFalse(self.consume("c"*32))

    def test_distinct_nonces_can_be_consumed(self):
        self.assertTrue(self.consume("d"*32, run_id=123))
        self.assertTrue(self.consume("e"*32, run_id=124))

    def test_rollback_does_not_burn_nonce(self):
        nonce = "f"*32
        with psycopg.connect(URL) as db:
            self.assertTrue(consume_nonce(db, nonce=nonce, run_id=123,
                            issue_number=39, head_sha="a"*40, project_id="proj_agent"))
            db.rollback()
        self.assertTrue(self.consume(nonce))

    def test_invalid_nonce_rejected(self):
        with self.assertRaises(ValueError):
            self.consume("invalid")


if __name__ == "__main__":
    unittest.main()
