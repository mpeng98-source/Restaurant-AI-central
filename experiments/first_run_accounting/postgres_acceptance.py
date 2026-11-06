"""Explicit local Docker harness. No remote URL, credentials or database accepted.

Run: python experiments/first_run_accounting/postgres_acceptance.py
Requires the previously pulled pinned image below; never pulls implicitly.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import time
import tempfile
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
PROJECT = 'proj_Nkd1G85QX72VHwdQ8mEg8CRa'
OWNER = 'dev_agent_accounting_owner_v27'
VERIFIER = 'dev_agent_verifier_v27'
ROLES = ['dev_agent_cost_writer_v27', 'dev_agent_reserver_v27', VERIFIER,
         'dev_agent_settler_v27', 'dev_agent_failure_v27', 'dev_agent_auditor_v27']
NAME = 'local-canary-exception-' + uuid.uuid4().hex[:10]
IMAGE = 'postgres@sha256:5264710be20f409750ac6dc4e5706dcef929c87e241605463f0f9aefa932a8d9'
ENV = dict(os.environ)
for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):
    ENV.pop(key, None)
DOCKER = ['docker','--host=unix:///var/run/docker.sock']


def docker(*args, data=None, check=True):
    return subprocess.run(DOCKER+list(args),input=data,text=True,capture_output=True,
                          check=check,timeout=45,env=ENV)


def sql(statement, role='postgres', check=True):
    return docker('exec','-i','-e','PGPASSWORD=synthetic-local-only',NAME,'psql',
        '-X','-h','127.0.0.1','-U',role,'-d','dev_agent_control_db','-At',
        '-v','ON_ERROR_STOP=1',data=statement,check=check)


def wait_ready():
    for _ in range(100):
        if docker('exec','-e','PGPASSWORD=synthetic-local-only',NAME,'psql',
                  '-h','127.0.0.1','-U','postgres','-d','postgres','-Atc','SELECT 1',
                  check=False).returncode == 0:
            return
        time.sleep(.1)
    raise RuntimeError('local Postgres unavailable')


def invocation(**overrides):
    values=dict(project=PROJECT,issue='58',run='123',attempt='1',head='a'*40,
                task='b'*64,request='c'*64)
    values.update(overrides)
    args=[values[k] for k in ('project','issue','run','attempt','head','task','request')]
    return 'SELECT dev_agent_canary_exception.consume('+','.join(
        'NULL' if v is None else "'"+v.replace("'","''")+"'" for v in args)+');'


class PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.socket_dir = tempfile.TemporaryDirectory(prefix='canary-pg-socket-')
        os.chmod(cls.socket_dir.name, 0o777)
        cls.addClassCleanup(cls.socket_dir.cleanup)
        docker('image','inspect',IMAGE)
        docker('run','-d','--pull=never','--name',NAME,'--network=none',
               '--mount',f'type=bind,src={cls.socket_dir.name},dst=/var/run/postgresql',
               '--memory=512m','--cpus=1','-e','POSTGRES_PASSWORD=synthetic-local-only',
               IMAGE)
        def cleanup_container():
            docker('exec','-u','0',NAME,'chown','-R',f'{os.getuid()}:{os.getgid()}',
                   '/var/run/postgresql',check=False)
            docker('rm','-f','-v',NAME)
        cls.addClassCleanup(cleanup_container)
        wait_ready()
        docker('exec',NAME,'createdb','-U','postgres','dev_agent_control_db')
        sql(f'CREATE ROLE {OWNER} NOLOGIN NOINHERIT;'+''.join(
            f"CREATE ROLE {r} LOGIN NOINHERIT PASSWORD 'synthetic-local-only';" for r in ROLES)+
            "CREATE ROLE unrelated LOGIN PASSWORD 'synthetic-local-only';")

    def setUp(self):
        sql('DROP SCHEMA IF EXISTS dev_agent_canary_exception CASCADE;'
            'DROP SCHEMA IF EXISTS dev_agent_accounting CASCADE;')
        for name in ('0001_dev_agent_accounting.sql','0002_dev_agent_execution_gate.sql'):
            sql((ROOT/'ops/migrations'/name).read_text())
        sql(f'ALTER SCHEMA dev_agent_accounting OWNER TO {OWNER};'+
            'DO $$ DECLARE x record; BEGIN '
            "FOR x IN SELECT tablename FROM pg_tables WHERE schemaname='dev_agent_accounting' LOOP "
            f"EXECUTE format('ALTER TABLE dev_agent_accounting.%I OWNER TO {OWNER}',x.tablename); END LOOP; "
            "FOR x IN SELECT p.oid::regprocedure AS f FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='dev_agent_accounting' LOOP "
            f"EXECUTE format('ALTER FUNCTION %s OWNER TO {OWNER}',x.f); END LOOP; END $$;"+
            f"INSERT INTO dev_agent_accounting.project VALUES('{PROJECT}',true);")
        sql((ROOT/'experiments/first_run_accounting/exception.sql').read_text())
        from dev_agent_rollout import FUNCTIONS
        for role, function in FUNCTIONS.items():
            sql(f'GRANT USAGE ON SCHEMA dev_agent_accounting TO {role};'+
                "DO $$ DECLARE f regprocedure; BEGIN SELECT p.oid::regprocedure INTO f FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='dev_agent_accounting' AND p.proname='"+function+"'; EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO "+role+"',f); END $$;")
        sql(f'GRANT USAGE ON SCHEMA dev_agent_canary_exception TO {VERIFIER};'
            f'GRANT EXECUTE ON FUNCTION dev_agent_canary_exception.consume(text,bigint,bigint,integer,text,text,text) TO {VERIFIER};')
        self.arm()

    def test_full_existing_and_exception_auditor_with_grants(self):
        import psycopg
        from dev_agent_rollout import audit
        from exception_audit import audit_exception
        with psycopg.connect(host=self.socket_dir.name,dbname='dev_agent_control_db',
                user='dev_agent_auditor_v27',password='synthetic-local-only',autocommit=True) as conn:
            self.assertTrue(audit(conn,PROJECT))
            self.assertTrue(audit_exception(conn))
            sql('GRANT SELECT ON dev_agent_canary_exception.claim TO dev_agent_verifier_v27;')
            with self.assertRaises(ValueError):audit_exception(conn)
            sql('REVOKE SELECT ON dev_agent_canary_exception.claim FROM dev_agent_verifier_v27;')
            self.assertTrue(audit_exception(conn))

    def test_auditor_rejects_unrelated_and_delegable_grants(self):
        import psycopg
        from exception_audit import audit_exception
        cases=[
            ('SELECT ON dev_agent_canary_exception.policy','unrelated'),
            ('INSERT ON dev_agent_canary_exception.claim','unrelated'),
            ('UPDATE (singleton) ON dev_agent_canary_exception.policy','unrelated'),
            ('SELECT ON dev_agent_canary_exception.claim','PUBLIC'),
            ('CREATE ON SCHEMA dev_agent_canary_exception','unrelated'),
            ('USAGE ON SCHEMA dev_agent_canary_exception','dev_agent_verifier_v27 WITH GRANT OPTION'),
            ('EXECUTE ON FUNCTION dev_agent_canary_exception.consume(text,bigint,bigint,integer,text,text,text)','dev_agent_verifier_v27 WITH GRANT OPTION'),
        ]
        with psycopg.connect(host=self.socket_dir.name,dbname='dev_agent_control_db',
                user='dev_agent_auditor_v27',password='synthetic-local-only',autocommit=True) as conn:
            for privilege,grantee in cases:
                with self.subTest(privilege=privilege,grantee=grantee):
                    sql(f'GRANT {privilege} TO {grantee};')
                    with self.assertRaises(ValueError):audit_exception(conn)
                    if ' WITH GRANT OPTION' in grantee:
                        sql(f'REVOKE GRANT OPTION FOR {privilege} FROM {grantee.split()[0]};')
                    else:
                        sql(f'REVOKE {privilege} FROM {grantee};')
                    self.assertTrue(audit_exception(conn))

    def arm(self):
        # Test-only administrator setup; this is NOT included in candidate SQL.
        sql("INSERT INTO dev_agent_canary_exception.policy VALUES(true,'"+PROJECT+
            "',58,123,1,'"+'a'*40+"','"+'b'*64+"','"+'c'*64+"','"+'d'*64+
            "',clock_timestamp(),LEAST(clock_timestamp()+interval '10 minutes',"
            "((clock_timestamp() AT TIME ZONE 'America/Los_Angeles')::date+1)::timestamp AT TIME ZONE 'America/Los_Angeles'),5,'unknown');")

    def consume(self, **overrides):
        return sql(invocation(**overrides),VERIFIER).stdout.strip()

    def test_valid_once_unknown_preserved(self):
        self.assertEqual(self.consume(),'t')
        self.assertEqual(self.consume(),'f')
        self.assertEqual(sql('SELECT prior_cost_state FROM dev_agent_canary_exception.policy').stdout.strip(),'unknown')
        self.assertEqual(sql('SELECT outcome FROM dev_agent_canary_exception.claim').stdout.strip(),'unknown_no_retry')
        self.assertEqual(sql('SELECT count(*) FROM dev_agent_accounting.cost_evidence').stdout.strip(),'0')

    def test_roles_cannot_read_mutate_or_rearm(self):
        for role in ROLES+['unrelated']:
            for table in ('policy','claim'):
                for statement in (f'SELECT * FROM dev_agent_canary_exception.{table};',
                                  f'INSERT INTO dev_agent_canary_exception.{table} DEFAULT VALUES;',
                                  f'UPDATE dev_agent_canary_exception.{table} SET singleton=true;',
                                  f'DELETE FROM dev_agent_canary_exception.{table};',
                                  f'TRUNCATE dev_agent_canary_exception.{table};'):
                    self.assertNotEqual(sql(statement,role,check=False).returncode,0)
            self.assertNotEqual(sql(f'SET ROLE {OWNER};',role,check=False).returncode,0)
            if role != VERIFIER:
                self.assertNotEqual(sql(invocation(),role,check=False).returncode,0)

    def test_wrong_bindings_and_null_deny(self):
        for field,value in [('project','proj_other'),('issue','59'),('run','124'),
                            ('attempt','2'),('head','e'*40),('task','e'*64),('request','e'*64)]:
            for wrong in (value,None):
                self.assertEqual(self.consume(**{field:wrong}),'f')
        self.assertEqual(sql('SELECT count(*) FROM dev_agent_canary_exception.claim').stdout.strip(),'0')

    def test_expiry_absence_and_stop(self):
        sql("UPDATE dev_agent_canary_exception.policy SET valid_from=clock_timestamp()-interval '20 minutes',valid_until=clock_timestamp()-interval '10 minutes';")
        self.assertEqual(self.consume(),'f')
        sql('DELETE FROM dev_agent_canary_exception.policy;')
        self.assertEqual(self.consume(),'f')
        self.arm()
        sql('UPDATE dev_agent_accounting.project SET enabled=false;')
        self.assertEqual(self.consume(),'f')

    def test_concurrent_consumers_one_winner(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.consume(),range(4)))
        self.assertEqual(sorted(results),['f','f','f','t'])

    def test_explicit_rollback_does_not_authorize(self):
        result=sql('BEGIN;'+invocation()+'ROLLBACK;',VERIFIER).stdout
        self.assertIn('t',result)
        # Adapter must not publish this intermediate result before commit.
        self.assertEqual(sql('SELECT count(*) FROM dev_agent_canary_exception.claim').stdout.strip(),'0')
        self.assertEqual(self.consume(),'t')

    def test_committed_claim_survives_restart(self):
        self.assertEqual(self.consume(),'t')
        docker('restart',NAME)
        wait_ready()
        self.assertEqual(self.consume(),'f')

    def test_disconnect_uncommitted_transaction_rolls_back(self):
        process=subprocess.Popen(DOCKER+['exec','-i','-e','PGPASSWORD=synthetic-local-only',NAME,
            'psql','-X','-h','127.0.0.1','-U',VERIFIER,'-d','dev_agent_control_db','-At',
            '-v','ON_ERROR_STOP=1'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,env=ENV)
        process.stdin.write("SET application_name='exception_failure_fixture';BEGIN;"+invocation()+"SELECT pg_sleep(30);\n")
        process.stdin.flush()
        try:
            for _ in range(50):
                active=sql("SELECT count(*) FROM pg_stat_activity WHERE application_name='exception_failure_fixture' AND wait_event='PgSleep';").stdout.strip()
                if active=='1':break
                time.sleep(.05)
            self.assertEqual(active,'1')
            sql("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='exception_failure_fixture';")
            process.communicate(timeout=5)
            self.assertNotEqual(process.returncode,0)
            self.assertEqual(sql('SELECT count(*) FROM dev_agent_canary_exception.claim').stdout.strip(),'0')
            self.assertEqual(self.consume(),'t')
        finally:
            if process.poll() is None:
                process.kill();process.communicate()

    def test_pending_normal_reservation_denies(self):
        sql("INSERT INTO dev_agent_accounting.cost_evidence VALUES('"+'f'*64+"','"+PROJECT+
            "',(now() AT TIME ZONE 'UTC')::date,now(),now(),0,9,1);"
            "INSERT INTO dev_agent_accounting.reservation(run_id,issue_number,head_sha,project_id,utc_day,cost_digest,run_attempt,task_digest) VALUES(9,9,'"+
            'a'*40+"','"+PROJECT+"',(now() AT TIME ZONE 'UTC')::date,'"+'f'*64+"',1,'"+'b'*64+"');")
        self.assertEqual(self.consume(),'f')

    def seed_normal_cost(self):
        sql("INSERT INTO dev_agent_accounting.cost_evidence VALUES('"+'f'*64+"','"+PROJECT+
            "',(now() AT TIME ZONE 'UTC')::date,now(),now(),0,9,1);")

    def normal_reserve(self):
        return sql("SELECT dev_agent_accounting.reserve_task(999,1,59,'"+'a'*40+"','"+
            PROJECT+"','"+'f'*64+"','"+'b'*64+"');",'dev_agent_reserver_v27').stdout.strip()

    def test_exception_then_normal_denied_even_after_restart(self):
        self.seed_normal_cost()
        self.assertEqual(self.consume(),'t')
        self.assertEqual(self.normal_reserve(),'f')
        docker('restart',NAME);wait_ready()
        self.assertEqual(self.normal_reserve(),'f')
        self.assertEqual(sql('SELECT count(*) FROM dev_agent_accounting.reservation').stdout.strip(),'0')

    def test_normal_then_exception_denied(self):
        self.seed_normal_cost()
        self.assertEqual(self.normal_reserve(),'t')
        self.assertEqual(self.consume(),'f')
        self.assertEqual(sql('SELECT count(*) FROM dev_agent_canary_exception.claim').stdout.strip(),'0')

    def snapshot_admission(self, stale_path, isolation):
        import psycopg
        self.seed_normal_cost()
        role=VERIFIER if stale_path=='exception' else 'dev_agent_reserver_v27'
        with psycopg.connect(host=self.socket_dir.name,dbname='dev_agent_control_db',
                user=role,password='synthetic-local-only',autocommit=True) as conn:
            conn.execute('BEGIN ISOLATION LEVEL '+isolation)
            # Establish the snapshot BEFORE the competing transaction commits.
            conn.execute('SELECT txid_current_snapshot()').fetchone()
            winner=self.normal_reserve() if stale_path=='exception' else self.consume()
            self.assertEqual(winner,'t')
            statement=invocation() if stale_path=='exception' else (
                "SELECT dev_agent_accounting.reserve_task(999,1,59,'"+'a'*40+"','"+
                PROJECT+"','"+'f'*64+"','"+'b'*64+"');")
            result=conn.execute(statement).fetchone()[0]
            conn.execute('COMMIT')
        counts=(int(sql('SELECT count(*) FROM dev_agent_canary_exception.claim').stdout),
                int(sql('SELECT count(*) FROM dev_agent_accounting.reservation').stdout))
        self.assertEqual((result,sum(counts)),(False,1),
                         f'{isolation} stale {stale_path}: result={result}, counts={counts}')

    def test_repeatable_read_stale_normal(self):
        self.snapshot_admission('normal','REPEATABLE READ')

    def test_repeatable_read_stale_exception(self):
        self.snapshot_admission('exception','REPEATABLE READ')

    def test_read_committed_old_statement_normal(self):
        self.snapshot_admission('normal','READ COMMITTED')

    def test_read_committed_old_statement_exception(self):
        self.snapshot_admission('exception','READ COMMITTED')

    def lock_wait_admission(self, winner_path):
        import psycopg
        self.seed_normal_cost()
        normal="SELECT dev_agent_accounting.reserve_task(999,1,59,'"+'a'*40+"','"+PROJECT+"','"+'f'*64+"','"+'b'*64+"');"
        winner_stmt,winner_role=(invocation(),VERIFIER) if winner_path=='exception' else (normal,'dev_agent_reserver_v27')
        loser_stmt,loser_role=(normal,'dev_agent_reserver_v27') if winner_path=='exception' else (invocation(),VERIFIER)
        def connect(role):
            return psycopg.connect(host=self.socket_dir.name,dbname='dev_agent_control_db',
                user=role,password='synthetic-local-only',autocommit=True)
        with connect(winner_role) as winner, connect(loser_role) as loser:
            winner.execute('BEGIN ISOLATION LEVEL READ COMMITTED')
            self.assertTrue(winner.execute(winner_stmt).fetchone()[0])
            loser.execute('BEGIN ISOLATION LEVEL READ COMMITTED')
            loser.execute("SET application_name='exception_lock_wait_fixture'")
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(lambda:loser.execute(loser_stmt).fetchone()[0])
                try:
                    for _ in range(100):
                        waiting=sql("SELECT count(*) FROM pg_stat_activity WHERE application_name='exception_lock_wait_fixture' AND wait_event='advisory';").stdout.strip()
                        if waiting=='1':break
                        time.sleep(.02)
                    self.assertEqual(waiting,'1','loser must enter statement before winner commits')
                finally:
                    winner.execute('COMMIT')
                self.assertFalse(future.result(timeout=5))
            loser.execute('COMMIT')
        self.assertEqual(int(sql('SELECT count(*) FROM dev_agent_canary_exception.claim').stdout)+
                         int(sql('SELECT count(*) FROM dev_agent_accounting.reservation').stdout),1)

    def test_read_committed_waits_for_exception_commit(self):
        self.lock_wait_admission('exception')

    def test_read_committed_waits_for_normal_commit(self):
        self.lock_wait_admission('normal')

    def test_unsupported_isolation_denies_without_competitor(self):
        self.seed_normal_cost()
        # Reject even SERIALIZABLE and PostgreSQL's RC-like READ UNCOMMITTED;
        # callers must explicitly use the one tested transaction contract.
        for isolation in ('REPEATABLE READ','SERIALIZABLE','READ UNCOMMITTED'):
            for statement,role in ((invocation(),VERIFIER),(
                "SELECT dev_agent_accounting.reserve_task(999,1,59,'"+'a'*40+"','"+
                PROJECT+"','"+'f'*64+"','"+'b'*64+"');",'dev_agent_reserver_v27')):
                with self.subTest(isolation=isolation,role=role):
                    result=sql('BEGIN ISOLATION LEVEL '+isolation+';'+statement+'COMMIT;',role)
                    self.assertIn('f',result.stdout.splitlines())
        self.assertEqual(sql('SELECT count(*) FROM dev_agent_canary_exception.claim').stdout.strip(),'0')
        self.assertEqual(sql('SELECT count(*) FROM dev_agent_accounting.reservation').stdout.strip(),'0')

    def test_mixed_concurrency_exactly_one_winner(self):
        import threading
        self.seed_normal_cost()
        barrier=threading.Barrier(2)
        def call(function):
            barrier.wait(timeout=5)
            return function()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(call,[self.consume,self.normal_reserve]))
        self.assertEqual(sorted(results),['f','t'])
        count=int(sql('SELECT count(*) FROM dev_agent_canary_exception.claim').stdout)+int(
            sql('SELECT count(*) FROM dev_agent_accounting.reservation').stdout)
        self.assertEqual(count,1)


if __name__=='__main__':
    sys.path.insert(0,str(ROOT/'scripts'))
    unittest.main(verbosity=2)
