"""Ephemeral PostgreSQL least-privilege SECURITY DEFINER acceptance.

Uses CI's disposable PostgreSQL superuser only. NEVER run against Neon.
"""
import os
from pathlib import Path
import unittest
from concurrent.futures import ThreadPoolExecutor
import psycopg

URL = os.environ.get("DEV_AGENT_TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(URL, "ephemeral PostgreSQL required")
class PermitFunctionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(URL, autocommit=True) as db:
            db.execute("CREATE SCHEMA IF NOT EXISTS dev_agent_control")
            db.execute((ROOT/"ops/dev-agent-control-schema.sql").read_text())
            db.execute((ROOT/"ops/dev-agent-permit-ledger-draft.sql").read_text())
            db.execute((ROOT/"ops/dev-agent-consume-permit-function-review.sql").read_text())
            db.execute("DROP ROLE IF EXISTS dev_agent_ci_verifier")
            db.execute("CREATE ROLE dev_agent_ci_verifier NOLOGIN")
            db.execute("GRANT USAGE ON SCHEMA dev_agent_control TO dev_agent_ci_verifier")
            db.execute("GRANT EXECUTE ON FUNCTION dev_agent_control.consume_verified_permit(text,bigint,bigint,text,text) TO dev_agent_ci_verifier")

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(URL, autocommit=True) as db:
            db.execute("REVOKE ALL ON FUNCTION dev_agent_control.consume_verified_permit(text,bigint,bigint,text,text) FROM dev_agent_ci_verifier")
            db.execute("REVOKE USAGE ON SCHEMA dev_agent_control FROM dev_agent_ci_verifier")
            db.execute("DROP ROLE IF EXISTS dev_agent_ci_verifier")
            db.execute("DROP FUNCTION IF EXISTS dev_agent_control.consume_verified_permit(text,bigint,bigint,text,text)")
            db.execute("DROP TABLE IF EXISTS dev_agent_control.consumed_permit")
            db.execute("DELETE FROM dev_agent_control.run_reservation WHERE project_id='proj_permit_ci'")
            db.execute("DELETE FROM dev_agent_control.daily_budget WHERE project_id='proj_permit_ci'")

    def setUp(self):
        with psycopg.connect(URL) as db:
            db.execute("DELETE FROM dev_agent_control.consumed_permit")
            db.execute("DELETE FROM dev_agent_control.run_reservation WHERE project_id='proj_permit_ci'")
            db.execute("DELETE FROM dev_agent_control.daily_budget WHERE project_id='proj_permit_ci'")
            db.execute("INSERT INTO dev_agent_control.daily_budget(project_id,utc_day,max_runs,daily_budget_usd) VALUES ('proj_permit_ci', CURRENT_DATE,6,10)")
            db.execute("INSERT INTO dev_agent_control.run_reservation(run_id,project_id,utc_day,issue_number,reserved_usd) VALUES (88001,'proj_permit_ci',CURRENT_DATE,39,5)")

    def call(self, nonce, run_id=88001, issue=39, project="proj_permit_ci"):
        with psycopg.connect(URL) as db:
            db.execute("SET ROLE dev_agent_ci_verifier")
            return db.execute(
                "SELECT dev_agent_control.consume_verified_permit(%s,%s,%s,%s,%s)",
                (nonce,run_id,issue,"a"*40,project)).fetchone()[0]

    def test_concurrent_only_one_consumes(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            values=list(pool.map(lambda _: self.call("b"*32),range(8)))
        self.assertEqual(values.count(True),1)
        self.assertEqual(values.count(False),7)

    def test_different_nonce_same_run_rejected(self):
        self.assertTrue(self.call("c"*32))
        self.assertFalse(self.call("d"*32))

    def test_wrong_issue_project_and_run_denied(self):
        self.assertFalse(self.call("e"*32,issue=40))
        self.assertFalse(self.call("f"*32,project="proj_wrong"))
        self.assertFalse(self.call("1"*32,run_id=99999))

    def test_verifier_cannot_directly_write_ledger(self):
        with psycopg.connect(URL) as db:
            db.execute("SET ROLE dev_agent_ci_verifier")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                db.execute("INSERT INTO dev_agent_control.consumed_permit(nonce,run_id,issue_number,head_sha,project_id) VALUES (%s,88001,39,%s,'proj_permit_ci')",("2"*32,"a"*40))

    def test_non_reserved_run_denied(self):
        with psycopg.connect(URL) as db:
            db.execute("UPDATE dev_agent_control.run_reservation SET state='started' WHERE run_id=88001")
        self.assertFalse(self.call("3"*32))


if __name__=="__main__":
    unittest.main()
