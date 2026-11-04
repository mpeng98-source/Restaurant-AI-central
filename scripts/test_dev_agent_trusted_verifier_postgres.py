"""Real PostgreSQL trusted signature + atomic nonce acceptance (ephemeral CI only)."""
import os
import secrets
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import psycopg
from dev_agent_signed_evidence import sign
from dev_agent_trusted_verifier import verify_and_consume

URL=os.environ.get("DEV_AGENT_TEST_DATABASE_URL")
ROOT=Path(__file__).resolve().parents[1]
KEY=b"test-only-ephemeral-signing-key-32bytes!!"
SHA="a"*40

@unittest.skipUnless(URL,"ephemeral PostgreSQL required")
class TrustedVerifierPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(URL,autocommit=True) as db:
            db.execute("CREATE SCHEMA IF NOT EXISTS dev_agent_control")
            db.execute((ROOT/"ops/dev-agent-control-schema.sql").read_text())
            db.execute((ROOT/"ops/dev-agent-permit-ledger-draft.sql").read_text())
            db.execute((ROOT/"ops/dev-agent-consume-permit-function-review.sql").read_text())
            db.execute("DROP ROLE IF EXISTS dev_agent_trusted_ci")
            db.execute("CREATE ROLE dev_agent_trusted_ci NOLOGIN")
            db.execute("GRANT USAGE ON SCHEMA dev_agent_control TO dev_agent_trusted_ci")
            db.execute("GRANT EXECUTE ON FUNCTION dev_agent_control.consume_verified_permit(text,bigint,bigint,text,text) TO dev_agent_trusted_ci")

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(URL,autocommit=True) as db:
            db.execute("REVOKE ALL ON FUNCTION dev_agent_control.consume_verified_permit(text,bigint,bigint,text,text) FROM dev_agent_trusted_ci")
            db.execute("REVOKE USAGE ON SCHEMA dev_agent_control FROM dev_agent_trusted_ci")
            db.execute("DROP ROLE IF EXISTS dev_agent_trusted_ci")
            db.execute("DROP FUNCTION IF EXISTS dev_agent_control.consume_verified_permit(text,bigint,bigint,text,text)")
            db.execute("DROP TABLE IF EXISTS dev_agent_control.consumed_permit")
            db.execute("DELETE FROM dev_agent_control.run_reservation WHERE project_id='proj_trusted_ci'")
            db.execute("DELETE FROM dev_agent_control.daily_budget WHERE project_id='proj_trusted_ci'")

    def setUp(self):
        self.run_id=secrets.randbelow(10**10)+10**10
        self.now=int(datetime.now(timezone.utc).timestamp())
        with psycopg.connect(URL) as db:
            db.execute("DELETE FROM dev_agent_control.consumed_permit")
            db.execute("DELETE FROM dev_agent_control.run_reservation WHERE project_id='proj_trusted_ci'")
            db.execute("DELETE FROM dev_agent_control.daily_budget WHERE project_id='proj_trusted_ci'")
            db.execute("INSERT INTO dev_agent_control.daily_budget(project_id,utc_day,max_runs,daily_budget_usd) VALUES ('proj_trusted_ci',CURRENT_DATE,6,10)")
            db.execute("INSERT INTO dev_agent_control.run_reservation(run_id,project_id,utc_day,issue_number,reserved_usd) VALUES (%s,'proj_trusted_ci',CURRENT_DATE,39,5)",(self.run_id,))

    def envelope(self,nonce=None,expires=None):
        return sign({"kind":"codex_permit","run_id":self.run_id,"issue_number":39,
                     "head_sha":SHA,"project_id":"proj_trusted_ci",
                     "issued_at":self.now-1,"expires_at":expires or self.now+120,
                     "nonce":nonce or secrets.token_hex(20)},KEY)

    def consume(self,e):
        with psycopg.connect(URL) as db:
            db.execute("SET ROLE dev_agent_trusted_ci")
            return verify_and_consume(db,e,KEY,now=self.now,run_id=self.run_id,
                                      issue_number=39,head_sha=SHA,project_id="proj_trusted_ci")

    def test_parallel_only_one_success(self):
        e=self.envelope()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.consume(e),range(8)))
        self.assertEqual(results.count(True),1)
        self.assertEqual(results.count(False),7)

    def test_different_nonce_same_run_denied(self):
        self.assertTrue(self.consume(self.envelope()))
        self.assertFalse(self.consume(self.envelope()))

    def test_tamper_expiry_denied_without_consumption(self):
        e=self.envelope()
        e["payload"]["issue_number"]=40
        with self.assertRaises(ValueError):
            self.consume(e)
        with self.assertRaises(ValueError):
            self.consume(self.envelope(expires=self.now-1))
        self.assertTrue(self.consume(self.envelope()))

    def test_direct_insert_denied(self):
        with psycopg.connect(URL) as db:
            db.execute("SET ROLE dev_agent_trusted_ci")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                db.execute("INSERT INTO dev_agent_control.consumed_permit(nonce,run_id,issue_number,head_sha,project_id) VALUES (%s,%s,39,%s,'proj_trusted_ci')",
                           (secrets.token_hex(20),self.run_id,SHA))

if __name__=="__main__":
    unittest.main()
