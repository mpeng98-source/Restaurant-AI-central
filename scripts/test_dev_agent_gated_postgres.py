"""Full real-PostgreSQL chain with a fake model; no billing/Neon/model calls."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
from pathlib import Path
import time
import unittest
from unittest.mock import MagicMock

import psycopg
from psycopg import sql

import test_dev_agent_accounting_postgres as fixture
from test_dev_agent_execution_gate import CTX, snapshot
from dev_agent_execution_gate import select, reserve, authorize, execute_simulated, service_identity
from dev_agent_rollout import audit
from dev_agent_migration_bundle import bundle

ROOT=Path(__file__).resolve().parents[1]


class GatedPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.AccountingPostgresTests.setUpClass.__func__(cls)
        old=cls.roles.copy()
        with psycopg.connect(cls.url,autocommit=True) as db:
            db.execute((ROOT/'ops/migrations/0002_dev_agent_execution_gate.sql').read_text())
            for name in old.values():
                db.execute(sql.SQL('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA dev_agent_accounting FROM {}').format(sql.Identifier(name)))
                db.execute(sql.SQL('REVOKE ALL ON SCHEMA dev_agent_accounting FROM {}').format(sql.Identifier(name)))
            db.execute((ROOT/'ops/dev-agent-v27-provision-review.sql').read_text())
        with psycopg.connect(cls.admin,autocommit=True) as db:
            for key,name in old.items():
                if key!='stranger':db.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(name)))
        cls.roles={'owner':'dev_agent_accounting_owner_v27','ingest':'dev_agent_cost_writer_v27',
                   'reserve':'dev_agent_reserver_v27','verify':'dev_agent_verifier_v27',
                   'settle':'dev_agent_settler_v27','failure':'dev_agent_failure_v27',
                   'audit':'dev_agent_auditor_v27','stranger':old['stranger']}

    tearDownClass=classmethod(fixture.AccountingPostgresTests.tearDownClass.__func__)
    connection=fixture.AccountingPostgresTests.connection
    cost_report=fixture.AccountingPostgresTests.cost_report
    age=fixture.AccountingPostgresTests.age

    def setUp(self):
        fixture.AccountingPostgresTests.setUp(self)
        self.ctx=replace(CTX,run_id=self.rid,project_id=self.project)
        self.plan=select(snapshot(),self.ctx)

    def reserve(self,ctx=None,plan=None):
        with self.connection('reserve') as db:
            return reserve(db,plan or self.plan,fixture.PERMIT_KEY,ctx=ctx or self.ctx,cost_digest=self.cost,now=int(time.time()))

    def authorize(self,e,ctx=None,plan=None):
        with self.connection('verify') as db:
            return authorize(db,plan or self.plan,e,fixture.PERMIT_KEY,ctx=ctx or self.ctx,now=int(time.time()))

    def test_full_chain_calls_fake_model_once_and_denies_replay(self):
        e=self.reserve();receipt=self.authorize(e);model=MagicMock(return_value={'files':[]})
        execute_simulated(receipt,self.plan,model,ctx=self.ctx,now=int(time.time()))
        model.assert_called_once()
        with self.assertRaises(ValueError):self.authorize(e)

    def test_eight_authorizers_only_one_can_admit(self):
        e=self.reserve()
        def attempt(_):
            try:self.authorize(e);return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(attempt,range(8)))
        self.assertEqual(results.count(True),1)

    def test_attempt_or_task_change_denied_before_model(self):
        e=self.reserve();model=MagicMock()
        other=replace(self.ctx,attempt=2)
        with self.assertRaises(ValueError):select(snapshot(),other)
        changed=snapshot();changed['issues'][0]['body']+=' Extra sentence.'
        other_plan=select(changed,self.ctx)
        with self.assertRaises(ValueError):self.authorize(e,self.ctx,other_plan)
        model.assert_not_called()
        self.authorize(e)

    def test_different_run_cannot_reserve_same_pending_issue(self):
        self.reserve()
        other=replace(self.ctx,run_id=self.rid+1)
        with self.assertRaises(psycopg.errors.UniqueViolation):self.reserve(other,select(snapshot(),other))

    def test_model_failure_never_releases_reservation(self):
        receipt=self.authorize(self.reserve())
        def fail(_):raise RuntimeError('fake executor failed')
        with self.assertRaises(RuntimeError):execute_simulated(receipt,self.plan,fail,ctx=self.ctx,now=int(time.time()))
        with self.connection('failure') as db:
            self.assertTrue(db.execute('SELECT dev_agent_accounting.mark_failed(%s,%s)',(self.rid,self.project)).fetchone()[0])
        with psycopg.connect(self.url) as db:
            self.assertEqual(db.execute('SELECT state FROM dev_agent_accounting.reservation WHERE run_id=%s',(self.rid,)).fetchone()[0],'failed_unreconciled')

    def test_cancelled_or_rolled_back_authorization_cannot_admit(self):
        e=self.reserve()
        # Interrupt SQL before commit; independent service retry must still be
        # the first successful consumption, not accept an uncommitted receipt.
        with self.connection('verify') as db:
            with self.assertRaises(RuntimeError):
                with db.transaction():
                    self.assertTrue(db.execute('SELECT dev_agent_accounting.authorize_task(%s,%s,%s,%s,%s,%s,%s,now(),now()+interval \'1 minute\')',
                        (e['payload']['nonce'],self.rid,1,50,self.ctx.head_sha,self.project,self.plan['task_digest'])).fetchone()[0])
                    raise RuntimeError('abort')
        self.authorize(e)

    def test_old_raw_functions_denied_to_new_service_roles(self):
        for role in ('reserve','verify'):
            with self.subTest(role=role),self.connection(role) as db:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    db.execute('SELECT dev_agent_accounting.reserve_run(%s,50,%s,%s,%s)',(self.rid,self.ctx.head_sha,self.project,self.cost))

    def test_service_identity_rejects_admin_url_before_mutation(self):
        with psycopg.connect(self.url,autocommit=True) as db:
            with self.assertRaises(ValueError):service_identity(db,'dev_agent_reserver_v27',database=self.dbname)
        with self.connection('reserve') as db:
            service_identity(db,'dev_agent_reserver_v27',database=self.dbname)

    def test_readiness_checks_restricted_owners_grants_and_empty_legacy(self):
        with self.connection('audit') as db:
            self.assertTrue(audit(db,self.project,expected_database=self.dbname))

    def test_readiness_rejects_disabled_project_and_extra_execute_grant(self):
        with psycopg.connect(self.url,autocommit=True) as db:
            db.execute('UPDATE dev_agent_accounting.project SET enabled=false WHERE project_id=%s',(self.project,))
        with self.connection('audit') as db:
            with self.assertRaises(ValueError):audit(db,self.project,expected_database=self.dbname)
        with psycopg.connect(self.url,autocommit=True) as db:
            db.execute('UPDATE dev_agent_accounting.project SET enabled=true WHERE project_id=%s',(self.project,))
            db.execute(sql.SQL('GRANT EXECUTE ON FUNCTION dev_agent_accounting.reserve_run(bigint,bigint,text,text,text) TO {}').format(sql.Identifier(self.roles['reserve'])))
        try:
            with self.connection('audit') as db:
                with self.assertRaises(ValueError):audit(db,self.project,expected_database=self.dbname)
        finally:
            with psycopg.connect(self.url,autocommit=True) as db:
                db.execute(sql.SQL('REVOKE ALL ON FUNCTION dev_agent_accounting.reserve_run(bigint,bigint,text,text,text) FROM {}').format(sql.Identifier(self.roles['reserve'])))

    def test_invalid_and_expired_signature_never_start_model(self):
        from dev_agent_signed_evidence import sign
        import copy
        original=self.reserve();model=MagicMock()
        bad=copy.deepcopy(original);bad['signature']='0'*64
        now=int(time.time())
        expired=sign({**original['payload'],'issued_at':now-600,'expires_at':now-480},fixture.PERMIT_KEY)
        for envelope in (bad,expired):
            with self.assertRaises(ValueError):
                receipt=self.authorize(envelope)
                execute_simulated(receipt,self.plan,model,ctx=self.ctx,now=now)
        model.assert_not_called()

    def test_exceeded_budget_and_stale_cost_never_start_model(self):
        model=MagicMock()
        with psycopg.connect(self.url,autocommit=True) as db:
            db.execute('UPDATE dev_agent_accounting.cost_evidence SET reported_usd=6 WHERE digest=%s',(self.cost,))
        with self.assertRaises(ValueError):
            receipt=self.authorize(self.reserve())
            execute_simulated(receipt,self.plan,model,ctx=self.ctx,now=int(time.time()))
        with psycopg.connect(self.url,autocommit=True) as db:
            db.execute("""UPDATE dev_agent_accounting.cost_evidence SET reported_usd=0,
                observed_at=observed_at-interval '2 hours',window_end=observed_at-interval '2 hours',
                utc_day=((observed_at-interval '2 hours') AT TIME ZONE 'UTC')::date WHERE digest=%s""",(self.cost,))
        with self.assertRaises(ValueError):
            receipt=self.authorize(self.reserve())
            execute_simulated(receipt,self.plan,model,ctx=self.ctx,now=int(time.time()))
        model.assert_not_called()

    def test_unavailable_database_never_start_model(self):
        from unittest.mock import patch
        model=MagicMock()
        with patch.object(self,'connection',side_effect=psycopg.OperationalError('synthetic unavailable')):
            with self.assertRaises(psycopg.OperationalError):
                receipt=self.authorize(self.reserve())
                execute_simulated(receipt,self.plan,model,ctx=self.ctx,now=int(time.time()))
        model.assert_not_called()

    def test_cross_service_membership_denied_even_with_noinherit(self):
        with psycopg.connect(self.url,autocommit=True) as db:
            db.execute('GRANT dev_agent_settler_v27 TO dev_agent_reserver_v27')
        try:
            with self.connection('reserve') as db:
                with self.assertRaises(ValueError):
                    service_identity(db,'dev_agent_reserver_v27',database=self.dbname)
            with self.connection('audit') as db:
                with self.assertRaises(ValueError):audit(db,self.project,expected_database=self.dbname)
        finally:
            with psycopg.connect(self.url,autocommit=True) as db:
                db.execute('REVOKE dev_agent_settler_v27 FROM dev_agent_reserver_v27')

    def test_unsafe_legacy_login_blocks_readiness(self):
        with psycopg.connect(self.admin,autocommit=True) as db:
            db.execute('CREATE ROLE dev_agent_unsafe_legacy_fixture LOGIN CREATEDB')
        try:
            with self.connection('audit') as db:
                with self.assertRaises(ValueError):audit(db,self.project,expected_database=self.dbname)
        finally:
            with psycopg.connect(self.admin,autocommit=True) as db:
                db.execute('DROP ROLE dev_agent_unsafe_legacy_fixture')

    def test_atomic_single_statement_rollout_bundle(self):
        name=self.dbname+'_bundle'
        migrator='migration_actor_'+self.suffix
        from psycopg.conninfo import make_conninfo
        with psycopg.connect(self.admin,autocommit=True) as db:
            db.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER CREATEROLE NOCREATEDB INHERIT').format(sql.Identifier(migrator)))
            db.execute(sql.SQL('GRANT dev_agent_accounting_owner_v27 TO {} WITH ADMIN OPTION').format(sql.Identifier(migrator)))
            db.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(name),sql.Identifier(migrator)))
        try:
            source,statement,digest=bundle(ROOT)
            self.assertNotIn(';',statement);self.assertEqual(len(digest),64)
            with psycopg.connect(make_conninfo(self.url,dbname=name),autocommit=True) as db:
                db.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(migrator)))
                db.execute(statement)
                self.assertEqual(db.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='dev_agent_accounting'").fetchone()[0],8)
        finally:
            with psycopg.connect(self.admin,autocommit=True) as db:
                db.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
                db.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(migrator)))


if __name__=='__main__':unittest.main()
