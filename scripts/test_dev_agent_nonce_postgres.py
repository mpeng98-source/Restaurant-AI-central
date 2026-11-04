"""Real PostgreSQL single-use nonce acceptance.

Only run against ephemeral CI PostgreSQL. Never drop a schema on Neon.
"""
import os
import threading
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
        barrier = threading.Barrier(12)
        def compete(_):
            try:
                with psycopg.connect(URL) as db:
                    barrier.wait(timeout=10)
                    return consume_nonce(db, nonce=nonce, run_id=123, issue_number=39,
                                         head_sha="a"*40, project_id="proj_agent")
            except psycopg.errors.UniqueViolation as error:
                # Concurrent identical inserts can hit a secondary unique index
                # before ON CONFLICT (nonce) resolves. This is a denied loser,
                # not a successful second consumption. Do not hide other errors.
                if error.diag.constraint_name not in {
                    "consumed_permit_run_id_issue_number_head_sha_project_id_key",
                    "consumed_permit_run_id_key",
                }:
                    raise
                return False
        with ThreadPoolExecutor(max_workers=12) as pool:
            outcomes = list(pool.map(compete, range(12)))
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
        class IntentionalRollback(Exception):
            pass
        with psycopg.connect(URL) as db:
            try:
                with db.transaction():
                    self.assertTrue(consume_nonce(db, nonce=nonce, run_id=123,
                                    issue_number=39, head_sha="a"*40, project_id="proj_agent"))
                    raise IntentionalRollback()
            except IntentionalRollback:
                pass
        self.assertTrue(self.consume(nonce))

    def test_different_nonce_same_run_is_denied(self):
        self.assertTrue(self.consume("1"*32, run_id=700))
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self.consume("2"*32, run_id=700)

    def test_invalid_sha_and_project_constraints(self):
        with psycopg.connect(URL) as db:
            with self.assertRaises(psycopg.errors.CheckViolation):
                consume_nonce(db, nonce="3"*32, run_id=701, issue_number=39,
                              head_sha="NOT_A_SHA", project_id="proj_agent")
        with psycopg.connect(URL) as db:
            with self.assertRaises(psycopg.errors.CheckViolation):
                consume_nonce(db, nonce="4"*32, run_id=702, issue_number=39,
                              head_sha="a"*40, project_id="invalid")

    def test_invalid_nonce_rejected(self):
        with self.assertRaises(ValueError):
            self.consume("invalid")


if __name__ == "__main__":
    unittest.main()
