"""Disposable PostgreSQL acceptance. Refuses remote URLs and never uses Neon.

Each run creates/drops its own database and NOLOGIN roles. Fixture owner
credentials never reach the protected service functions under test.
"""
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import os
import secrets
import time
import unittest

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from dev_agent_accounting import reserve_and_sign, consume, finalize
from dev_agent_cost_evidence import Producer, sign_cost, ingest_cost
from dev_agent_signed_evidence import sign

ROOT=Path(__file__).resolve().parents[1]
KEY=b"disposable-cost-test-key-not-production!!"
PERMIT_KEY=b"disposable-permit-test-key-separate!!!"
REVIEW_KEY=b"disposable-review-test-key-separate!!!"
SHA="a"*40
PRODUCER=Producer("mpeng98-source/Restaurant-AI-central",
                  ".github/workflows/accounting-acceptance.yml",SHA,100,1)


class AccountingPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url=os.environ.get("DEV_AGENT_TEST_DATABASE_URL","")
        if not url or os.environ.get("DEV_AGENT_DISPOSABLE_TESTS")!="1":
            raise RuntimeError("explicit disposable test configuration required")
        params=conninfo_to_dict(url)
        if (params.get("host") not in {"localhost","127.0.0.1","::1"}
                or params.get("hostaddr") or params.get("service")):
            raise RuntimeError("only loopback PostgreSQL permitted")
        cls.admin=url
        cls.suffix=secrets.token_hex(6)
        cls.dbname="accounting_test_"+cls.suffix
        cls.roles={name:"acct_"+name+"_"+cls.suffix for name in
                   ("owner","ingest","reserve","verify","settle","failure","stranger")}
        with psycopg.connect(url,autocommit=True) as db:
            for role in cls.roles.values():
                db.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS").format(sql.Identifier(role)))
            db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(cls.dbname)))
        cls.url=make_conninfo(url,dbname=cls.dbname)
        with psycopg.connect(cls.url,autocommit=True) as db:
            db.execute((ROOT/"ops/migrations/0001_dev_agent_accounting.sql").read_text())
            db.execute(sql.SQL("ALTER SCHEMA dev_agent_accounting OWNER TO {}").format(sql.Identifier(cls.roles["owner"])))
            for table in ("project","cost_evidence","reservation","permit","settlement"):
                db.execute(sql.SQL("ALTER TABLE dev_agent_accounting.{} OWNER TO {}").format(sql.Identifier(table),sql.Identifier(cls.roles["owner"])))
            funcs={"ingest":"ingest_cost(text,text,date,timestamptz,timestamptz,numeric,bigint,integer)",
                   "reserve":"reserve_run(bigint,bigint,text,text,text)",
                   "verify":"consume_permit(text,bigint,bigint,text,text,timestamptz,timestamptz)",
                   "settle":"finalize_run(text,bigint,bigint,text,text,text,text,timestamptz,text)",
                   "failure":"mark_failed(bigint,text)"}
            for role,func in funcs.items():
                db.execute(sql.SQL("ALTER FUNCTION dev_agent_accounting."+func+" OWNER TO {}").format(sql.Identifier(cls.roles["owner"])))
                db.execute(sql.SQL("GRANT USAGE ON SCHEMA dev_agent_accounting TO {}").format(sql.Identifier(cls.roles[role])))
                db.execute(sql.SQL("GRANT EXECUTE ON FUNCTION dev_agent_accounting."+func+" TO {}").format(sql.Identifier(cls.roles[role])))

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,"url"): return
        with psycopg.connect(cls.admin,autocommit=True) as db:
            db.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(cls.dbname)))
            for role in cls.roles.values():
                db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))

    def setUp(self):
        self.project="proj_acceptance_"+secrets.token_hex(8)
        self.rid=secrets.randbelow(10**12)+10**12
        self.now=int(time.time())
        self.day=datetime.fromtimestamp(self.now,timezone.utc).date()
        with psycopg.connect(self.url) as db:
            db.execute("INSERT INTO dev_agent_accounting.project VALUES (%s,true)",(self.project,))
        self.cost=self.cost_report()

    def connection(self,role):
        db=psycopg.connect(self.url,autocommit=True)
        db.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(self.roles[role])))
        return db

    def binding(self,rid=None,sha=SHA):
        return dict(run_id=rid or self.rid,issue_number=39,head_sha=sha,project_id=self.project)

    def cost_report(self,*,amount="0.000000",day=None,end=None,observed=None):
        day=day or self.day
        start=int(datetime.combine(day,datetime.min.time(),timezone.utc).timestamp())
        end=end or min(self.now,start+86400)
        report={"project_id":self.project,"utc_day":day.isoformat(),"window_start":start,
                "window_end":end,"observed_at":observed or self.now,"reported_usd":amount,
                "source":"openai_organization_costs","project_rows":1}
        e=sign_cost(report,KEY,producer=PRODUCER,now=observed or self.now)
        with self.connection("ingest") as db:
            return ingest_cost(db,e,KEY,producer=PRODUCER,project_id=self.project,now=self.now)

    def reserve(self,rid=None,sha=SHA):
        with self.connection("reserve") as db:
            return reserve_and_sign(db,PERMIT_KEY,cost_digest=self.cost,now=int(time.time()),**self.binding(rid,sha))

    def consume(self,e,rid=None,sha=SHA):
        with self.connection("verify") as db:
            return consume(db,e,PERMIT_KEY,now=int(time.time()),**self.binding(rid,sha))

    def age(self,rid=None,days=0):
        with psycopg.connect(self.url) as db:
            db.execute("UPDATE dev_agent_accounting.reservation SET created_at=%s,utc_day=%s WHERE run_id=%s",
                       (datetime.now(timezone.utc)-timedelta(days=days,seconds=5),self.day-timedelta(days=days),rid or self.rid))

    def review(self,*,decision="cancelled_verified",rid=None,cost=None,finished=None,**extra):
        body={"kind":"settlement_review_v1","producer":asdict(PRODUCER),
              "issued_at":int(time.time()),"expires_at":int(time.time())+120,
              "binding":self.binding(rid),"decision":decision,"cost_digest":cost or self.cost,
              "finished_at":finished or int(time.time())-1,"review_reference":"review/acceptance/39",
              "never_started_reviewed":True,"billing_finality_reviewed":True,**extra}
        return sign(body,REVIEW_KEY)

    def finalize(self,e,rid=None):
        with self.connection("settle") as db:
            return finalize(db,e,REVIEW_KEY,producer=PRODUCER,now=int(time.time()),**self.binding(rid))

    def test_happy_chain_replay_and_cancel_after_consume_denied(self):
        e=self.reserve()
        self.assertTrue(self.consume(e))
        self.assertFalse(self.consume(e))
        self.age()
        self.assertFalse(self.finalize(self.review()))
        with psycopg.connect(self.url) as db:
            self.assertEqual(db.execute("SELECT state FROM dev_agent_accounting.reservation WHERE run_id=%s",(self.rid,)).fetchone()[0],"started")

    def test_parallel_consumers_exactly_one(self):
        e=self.reserve()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.consume(e),range(8)))
        self.assertEqual(results.count(True),1)
        self.assertEqual(results.count(False),7)

    def test_two_different_nonces_same_run_one_success(self):
        e=self.reserve()
        another=sign({**e["payload"],"nonce":secrets.token_hex(24)},PERMIT_KEY)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(self.consume,[e,another]))
        self.assertEqual(results.count(True),1)

    def test_signed_wrong_sha_cannot_consume_reservation(self):
        e=self.reserve()
        wrong=sign({**e["payload"],"head_sha":"f"*40},PERMIT_KEY)
        self.assertFalse(self.consume(wrong,sha="f"*40))
        self.assertTrue(self.consume(e))

    def test_parallel_reservations_obey_budget(self):
        def attempt(i):
            try:self.reserve(self.rid+i);return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(attempt,range(8)))
        self.assertEqual(results.count(True),2)

    def test_duplicate_reservation_does_not_issue_second_permit(self):
        self.reserve()
        with self.assertRaises(ValueError):self.reserve()

    def test_cancellation_idempotency_and_day_attempt_limit(self):
        for i in range(6):
            rid=self.rid+i
            self.reserve(rid);self.age(rid)
            proof=self.review(rid=rid)
            self.assertTrue(self.finalize(proof,rid))
            self.assertFalse(self.finalize(proof,rid))
        with self.assertRaises(ValueError):self.reserve(self.rid+7)

    def test_parallel_cancellation_once_and_released_only_once(self):
        self.reserve();self.age();e=self.review()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.finalize(e),range(8)))
        self.assertEqual(results.count(True),1)
        self.reserve(self.rid+1);self.reserve(self.rid+2)
        with self.assertRaises(ValueError):self.reserve(self.rid+3)

    def test_cancel_races_consume_with_no_reusable_permit(self):
        e=self.reserve();self.age();proof=self.review()
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(self.consume,e);b=pool.submit(self.finalize,proof)
            self.assertEqual([a.result(),b.result()].count(True),1)
        self.assertFalse(self.consume(e))

    def test_failed_run_keeps_reservation(self):
        e=self.reserve();self.consume(e)
        with self.connection("failure") as db:
            self.assertTrue(db.execute("SELECT dev_agent_accounting.mark_failed(%s,%s)",(self.rid,self.project)).fetchone()[0])
        self.reserve(self.rid+1)
        with self.assertRaises(ValueError):self.reserve(self.rid+2)

    def test_previous_day_pending_counts_against_today(self):
        self.reserve();self.age(days=1)
        self.reserve(self.rid+1)
        with self.assertRaises(ValueError):self.reserve(self.rid+2)

    def test_stale_or_untrusted_legacy_costs_cannot_reserve(self):
        with psycopg.connect(self.url) as db:
            db.execute("""UPDATE dev_agent_accounting.cost_evidence
              SET observed_at=observed_at-interval '2 hours',
                  window_end=observed_at-interval '2 hours',
                  utc_day=((observed_at-interval '2 hours') AT TIME ZONE 'UTC')::date
              WHERE digest=%s""",(self.cost,))
        with self.assertRaises(ValueError):self.reserve()

    def test_ingestion_replay_idempotent_and_regression_rejected(self):
        self.assertEqual(self.cost,self.cost_report())
        with self.assertRaises(psycopg.Error):
            self.cost_report(amount="1.000000") # same window, altered contents
        with self.assertRaises(psycopg.Error):
            self.cost_report(end=self.now-1)

    def test_decreasing_cost_and_superseded_snapshot_denied(self):
        # Seed prior observation metadata through the fixture owner, never a
        # service role. New evidence must not decrease reported daily spend.
        with psycopg.connect(self.url) as db:
            db.execute("UPDATE dev_agent_accounting.cost_evidence SET window_end=window_end-interval '1 second',reported_usd=2 WHERE digest=%s",(self.cost,))
        with self.assertRaises(psycopg.Error):self.cost_report(amount="1.000000")
        latest=self.cost_report(amount="2.000000")
        with self.assertRaises(ValueError):self.reserve()
        self.cost=latest
        self.reserve()

    def test_unknown_digest_and_other_project_cannot_authorize(self):
        self.cost="f"*64
        with self.assertRaises(ValueError):self.reserve()
        original=self.project
        self.project="proj_acceptance_other_"+secrets.token_hex(8)
        with psycopg.connect(self.url) as db:
            db.execute("INSERT INTO dev_agent_accounting.project VALUES (%s,true)",(self.project,))
        self.cost=self.cost_report()
        self.project=original
        with self.assertRaises(ValueError):self.reserve()

    def test_db_clock_rejects_expiry_even_if_python_clock_wrong(self):
        e=self.reserve();e=sign({**e["payload"],"issued_at":self.now-200,"expires_at":self.now-1},PERMIT_KEY)
        with self.connection("verify") as db:
            self.assertFalse(consume(db,e,PERMIT_KEY,now=self.now-100,**self.binding()))

    def test_disabled_project_blocks_reserve_and_consume(self):
        e=self.reserve()
        with psycopg.connect(self.url) as db:
            db.execute("UPDATE dev_agent_accounting.project SET enabled=false WHERE project_id=%s",(self.project,))
        self.assertFalse(self.consume(e))
        with self.assertRaises(ValueError):self.reserve(self.rid+1)

    def test_transaction_rollback_leaves_no_ingestion_or_reservation(self):
        with self.connection("reserve") as db:
            with self.assertRaises(RuntimeError):
                with db.transaction():
                    self.assertTrue(db.execute("SELECT dev_agent_accounting.reserve_run(%s,39,%s,%s,%s)",
                                             (self.rid,SHA,self.project,self.cost)).fetchone()[0])
                    raise RuntimeError("simulate aborted protected job")
        self.reserve()

    def test_no_direct_table_writes_or_cross_role_functions(self):
        for role in ("ingest","reserve","verify","settle","failure","stranger"):
            with self.subTest(role=role),self.connection(role) as db:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    db.execute("UPDATE dev_agent_accounting.project SET enabled=true")
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    db.execute("INSERT INTO dev_agent_accounting.permit VALUES (%s,%s,now())",("a"*32,self.rid))
                if role!="verify":
                    with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                        db.execute("SELECT dev_agent_accounting.consume_permit(%s,%s,39,%s,%s,now(),now()+interval '1 minute')",
                                   ("a"*32,self.rid,SHA,self.project))

    def test_settlement_needs_buffer_matching_cost_day_and_consumption(self):
        e=self.reserve();self.consume(e);self.age()
        self.assertFalse(self.finalize(self.review(decision="settled")))
        self.age(days=2)
        old=self.day-timedelta(days=2)
        old_cost=self.cost_report(day=old,amount="2.000000")
        finished=int(time.time())-2*86400+100
        proof=self.review(decision="settled",cost=old_cost,finished=finished)
        self.assertTrue(self.finalize(proof))
        self.assertFalse(self.finalize(proof))
        # Settled prior reservation is no longer charged a second $5 reserve.
        self.reserve(self.rid+1);self.reserve(self.rid+2)

    def test_settlement_wrong_project_or_day_cannot_release(self):
        e=self.reserve();self.consume(e);self.age(days=2)
        proof=self.review(decision="settled",finished=self.now-86401)
        self.assertFalse(self.finalize(proof))

    def test_parallel_reviewed_settlement_only_one_final_transition(self):
        e=self.reserve();self.consume(e);self.age(days=2)
        old_cost=self.cost_report(day=self.day-timedelta(days=2),amount="2.000000")
        proof=self.review(decision="settled",cost=old_cost,finished=self.now-2*86400+100)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.finalize(proof),range(8)))
        self.assertEqual(results.count(True),1)
        self.assertEqual(results.count(False),7)


if __name__=="__main__":
    unittest.main()
