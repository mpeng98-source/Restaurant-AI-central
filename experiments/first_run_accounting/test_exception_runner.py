from contextlib import contextmanager
from dataclasses import asdict, replace
import unittest
from unittest.mock import patch

from exception_runner import execute
from dev_agent_execution_gate import Context, digest_task


class Connection:
    def __init__(self, *, deny=False, commit_failure=False):
        self.events = []
        self.deny = deny
        self.commit_failure = commit_failure

    @contextmanager
    def transaction(self):
        self.events.append('begin')
        yield
        if self.commit_failure:
            raise OSError('ambiguous commit')
        self.events.append('commit')

    def execute(self, sql, args):
        self.events.append(('consume', args))
        return self

    def fetchone(self):
        return (not self.deny,)


class ExceptionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.ctx = Context('mpeng98-source/Restaurant-AI-central',
            '.github/workflows/chubby-dev-agent-gated.yml','refs/heads/main',
            'a'*40, 123, 1, 58, 'proj_Nkd1G85QX72VHwdQ8mEg8CRa')
        self.task = {'number':58,'title':'synthetic','body':'add'}
        self.plan = {'context':asdict(self.ctx),'task':self.task,
                     'task_digest':digest_task(self.task)}

    def invoke(self, conn, callback, ctx=None):
        with patch('exception_runner.service_identity') as identity:
            result = execute(conn,self.plan,ctx=ctx or self.ctx,
                request_digest='b'*64,callback=callback,clock=lambda:1000)
            identity.assert_called_once_with(conn,'dev_agent_verifier_v27')
            return result

    def test_dispatch_only_after_committed_claim(self):
        conn = Connection()
        def dispatch(receipt):
            self.assertEqual(conn.events[-1], 'commit')
            self.assertEqual(receipt['context'], asdict(self.ctx))
            self.assertEqual(receipt['admit_before'], 1300)
            return 'called once'
        self.assertEqual(self.invoke(conn, dispatch), 'called once')
        self.assertEqual(conn.events[1][1], (self.ctx.project_id,58,123,1,'a'*40,
                         self.plan['task_digest'],'b'*64))

    def test_missing_policy_and_uncertain_commit_never_dispatch(self):
        for conn in (Connection(deny=True),Connection(commit_failure=True)):
            called=[]
            with self.assertRaises((ValueError,OSError)):
                self.invoke(conn,lambda r:called.append(r))
            self.assertEqual(called,[])

    def test_failed_provider_has_no_retry_or_refund(self):
        conn=Connection(); calls=[]
        def fail(receipt):
            calls.append(receipt)
            raise TimeoutError('unknown provider outcome')
        with self.assertRaises(TimeoutError):
            self.invoke(conn,fail)
        self.assertEqual(len(calls),1)
        self.assertEqual(conn.events[-1],'commit')
        self.assertEqual(len(conn.events),3)

    def test_other_issue_project_head_attempt_or_task_denied(self):
        for ctx in (replace(self.ctx,issue_number=59),replace(self.ctx,attempt=2),
                    replace(self.ctx,project_id='proj_other'),replace(self.ctx,head_sha='c'*40)):
            conn=Connection()
            with self.assertRaises(ValueError):
                self.invoke(conn,lambda r:self.fail('dispatched'),ctx)
            self.assertEqual(conn.events,[])
        self.plan['task']['body']='changed'
        with self.assertRaises(ValueError):
            self.invoke(Connection(),lambda r:self.fail('dispatched'))


if __name__=='__main__':
    unittest.main()
