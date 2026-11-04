"""Offline acceptance: irreversible claim precedes the only billable request."""
import contextlib
import copy
import io
import os
from pathlib import Path
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import yaml

import dev_agent_bootstrap as b

NOW = 1793772000
SHA = 'a' * 40
TAG = 'b' * 40
ROOT = Path(__file__).resolve().parents[1]
ENV = {'GITHUB_REPOSITORY': b.REPOSITORY, 'GITHUB_EVENT_NAME': 'workflow_dispatch',
       'GITHUB_REF': 'refs/heads/main', 'GITHUB_WORKFLOW_REF': b.REPOSITORY+'/'+b.WORKFLOW+'@refs/heads/main',
       'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_SHA': SHA, 'GITHUB_RUN_ID': '123',
       'BOOTSTRAP_ENABLED': 'true', 'CODING_ENABLED': 'false', 'PROJECT_ID': b.PROJECT,
       'CONFIRMATION': b.CONFIRMATION, 'APPROVED_SHA': SHA,
       'GH_TOKEN': 'synthetic-github-secret', 'OPENAI_API_KEY': 'synthetic-model-secret'}
SETTINGS = {'can_admins_bypass': False,
            'protection_rules': [{'type': 'required_reviewers', 'prevent_self_review': True,
                                  'reviewers': [{'type': 'User', 'reviewer': {'id': 1}}]}],
            'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True}}
POLICIES = {'total_count': 1, 'branch_policies': [{'name': 'main', 'type': 'branch'}]}


class FakeTransport:
    def __init__(self):
        self.lock = threading.Lock()
        self.claimed = False
        self.calls = []
        self.model_calls = 0
        self.failure = None
        self.settings = copy.deepcopy(SETTINGS)
        self.policies = copy.deepcopy(POLICIES)
        self.main = SHA
        self.ruleset = {'target':'tag','enforcement':'active','bypass_actors':[],
                        'conditions':{'ref_name':{'include':[b.REF],'exclude':[]}},
                        'rules':[{'type':'update'},{'type':'deletion'}]}
        self.response = {'model': b.MODEL, 'status': 'completed',
                         'usage': {'input_tokens': 10, 'output_tokens': 1}}

    def request(self, url, token, *, method='GET', body=None, project=None):
        with self.lock:
            self.calls.append((url, method, body, project))
            if project is not None:
                assert self.claimed, 'model call before durable claim'
                assert token == ENV['OPENAI_API_KEY']
                assert body == b.PAYLOAD and project == b.PROJECT
                self.model_calls += 1
                if self.failure:
                    raise self.failure
                return self.response
            assert token == ENV['GH_TOKEN']
            if url.endswith('/rulesets?includes_parents=true&per_page=100'):
                return [{'id': 42}]
            if url.endswith('/rulesets/42'):
                return self.ruleset
            if url.endswith('/deployment-branch-policies'):
                return self.policies
            if url.endswith('/environments/'+b.ENVIRONMENT):
                return self.settings
            if url.endswith('/git/ref/heads/main'):
                return {'object': {'sha': self.main}}
            if url.endswith('/git/tags'):
                return {'sha': TAG}
            if url.endswith('/git/refs'):
                if self.claimed:
                    raise b.Denied()
                self.claimed = True
                return {'ref': b.REF, 'object': {'sha': TAG, 'type': 'tag'}}
            raise AssertionError('unexpected endpoint')


class BootstrapTests(unittest.TestCase):
    def test_success_fixed_probe_and_permanent_claim(self):
        t = FakeTransport()
        self.assertEqual(b.bootstrap(t, ENV, NOW), {'input_tokens': 10, 'output_tokens': 1})
        self.assertTrue(t.claimed)
        self.assertEqual(t.model_calls, 1)
        claim = t.calls[-2]
        self.assertEqual(claim[2], {'ref': b.REF, 'sha': TAG})
        binding = __import__('json').loads(t.calls[-3][2]['message'])
        self.assertEqual(binding['sha'], SHA)
        self.assertEqual(binding['run_id'], '123')
        self.assertEqual(binding['estimated_allowance_usd'], '0.01')

    def test_parallel_new_runs_allow_one_request_total(self):
        t = FakeTransport()
        def run(i):
            try:
                b.bootstrap(t, {**ENV, 'GITHUB_RUN_ID': str(1000+i)}, NOW)
                return True
            except b.Denied:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(run, range(8)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(t.model_calls, 1)

    def test_timeout_or_failure_burns_claim_without_retry(self):
        for error in (TimeoutError('private'), ValueError('private')):
            t = FakeTransport()
            t.failure = error
            with self.assertRaises(type(error)):
                b.bootstrap(t, ENV, NOW)
            with self.assertRaises(b.Denied):
                b.bootstrap(t, {**ENV, 'GITHUB_RUN_ID': '124'}, NOW)
            self.assertEqual(t.model_calls, 1)
            self.assertTrue(t.claimed)
            self.assertTrue(all(method not in ('PATCH', 'DELETE') for _, method, _, _ in t.calls))

    def test_bad_context_denies_before_network(self):
        changes = {'GITHUB_REPOSITORY': 'attacker/repo', 'GITHUB_EVENT_NAME': 'push',
                   'GITHUB_REF': 'refs/heads/feature', 'GITHUB_WORKFLOW_REF': 'forged',
                   'GITHUB_RUN_ATTEMPT': '2', 'BOOTSTRAP_ENABLED': 'false', 'CODING_ENABLED': 'true',
                   'PROJECT_ID': 'proj_wrong', 'CONFIRMATION': '', 'APPROVED_SHA': 'c'*40,
                   'GITHUB_RUN_ID': '0', 'GH_TOKEN': '', 'OPENAI_API_KEY': ''}
        for key, value in changes.items():
            with self.subTest(key=key):
                t = FakeTransport()
                with self.assertRaises(b.Denied):
                    b.bootstrap(t, {**ENV, key: value}, NOW)
                self.assertEqual(t.calls, [])
        with self.assertRaises(b.Denied):
            b.bootstrap(FakeTransport(), ENV, b.REVIEW_VALID_UNTIL)

    def test_missing_approval_or_wrong_main_branch_policy_denies_before_claim(self):
        cases = [({'protection_rules': []}, None), ({'can_admins_bypass': True}, None),
                 ({'deployment_branch_policy': None}, None),
                 ({'protection_rules': [{'type':'required_reviewers', 'prevent_self_review':False,
                                        'reviewers':[1]}]}, None),
                 ({}, {'total_count': 2, 'branch_policies': POLICIES['branch_policies']}),
                 ({}, {'total_count': 1, 'branch_policies': [{'name':'*','type':'branch'}]}),
                 ({}, {'total_count': 1, 'branch_policies': [{'name':'main','type':'tag'}]})]
        for settings, policies in cases:
            t = FakeTransport()
            t.settings.update(settings)
            if policies: t.policies = policies
            with self.assertRaises(b.Denied): b.bootstrap(t, ENV, NOW)
            self.assertFalse(t.claimed)
            self.assertEqual(t.model_calls, 0)
        t = FakeTransport(); t.main = 'c'*40
        with self.assertRaises(b.Denied): b.bootstrap(t, ENV, NOW)
        self.assertFalse(t.claimed)

    def test_unprotected_mutable_or_bypassable_tag_denies_before_claim(self):
        for change in ({'enforcement':'disabled'}, {'bypass_actors':[{'actor_id':1}]},
                       {'rules':[{'type':'deletion'}]}, {'target':'branch'},
                       {'conditions':{'ref_name':{'include':[b.REF],'exclude':[b.REF]}}}):
            t=FakeTransport();t.ruleset.update(change)
            with self.assertRaises(b.Denied): b.bootstrap(t, ENV, NOW)
            self.assertFalse(t.claimed)
            self.assertEqual(t.model_calls,0)

    def test_invalid_model_result_never_releases_claim(self):
        for change in ({'status':'incomplete'}, {'model':'other'},
                       {'usage':{'input_tokens':True,'output_tokens':1}},
                       {'usage':{'input_tokens':10,'output_tokens':17}}):
            t = FakeTransport(); t.response.update(change)
            with self.assertRaises(b.Denied): b.bootstrap(t, ENV, NOW)
            self.assertTrue(t.claimed)
            self.assertEqual(t.model_calls, 1)

    def test_exception_and_model_output_never_logged(self):
        err, out = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, ENV, clear=True), patch.object(b, 'Transport') as transport, \
                patch.object(b.time, 'time', return_value=NOW), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            transport.return_value.request.side_effect = ValueError('private-api-body-'+ENV['OPENAI_API_KEY'])
            self.assertEqual(b.main(), 2)
        self.assertNotIn('private-api-body', err.getvalue()+out.getvalue())
        self.assertNotIn(ENV['OPENAI_API_KEY'], err.getvalue()+out.getvalue())

    def test_transport_never_follows_redirect_or_uses_arbitrary_endpoint(self):
        with self.assertRaises(b.Denied): b.NoRedirect().redirect_request(None,None,302,'',{},'https://evil.test')
        t = b.Transport()
        with self.assertRaises(b.Denied): t.request('https://evil.test', 'secret')
        with self.assertRaises(b.Denied): t.request('https://evil.test', 'secret', project=b.PROJECT)

    def test_transport_sends_one_project_bound_request_without_retry(self):
        from unittest.mock import MagicMock
        transport = b.Transport()
        fake = MagicMock()
        fake.open.return_value.__enter__.return_value.read.return_value = b'{"ok":true}'
        transport.opener = fake
        self.assertEqual(transport.request('https://api.openai.com/v1/responses',
            'synthetic-secret', method='POST', body=b.PAYLOAD, project=b.PROJECT), {'ok': True})
        request = fake.open.call_args.args[0]
        self.assertEqual(request.get_header('Openai-project'), b.PROJECT)
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(__import__('json').loads(request.data), b.PAYLOAD)
        fake.open.assert_called_once()
        fake.open.reset_mock()
        fake.open.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            transport.request('https://api.openai.com/v1/responses', 'synthetic-secret',
                              method='POST', body=b.PAYLOAD, project=b.PROJECT)
        fake.open.assert_called_once()

    def test_workflow_manual_default_off_and_has_no_coding_or_db_secrets(self):
        wf = yaml.load((ROOT/b.WORKFLOW).read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(set(wf['on']), {'workflow_dispatch'})
        job = wf['jobs']['bootstrap']
        self.assertEqual(job['environment'], b.ENVIRONMENT)
        self.assertIn("github.run_attempt == 1", job['if'])
        self.assertIn("CHUBBY_DEV_AGENT_BOOTSTRAP_ENABLED == 'true'", job['if'])
        self.assertIn("CHUBBY_DEV_AGENT_GATED_ENABLED == 'false'", job['if'])
        self.assertEqual(job['steps'][-1]['run'], 'python scripts/dev_agent_bootstrap.py')
        self.assertEqual(set(job['steps'][-1]['env']), {'GH_TOKEN','OPENAI_API_KEY','PROJECT_ID',
                         'BOOTSTRAP_ENABLED','CODING_ENABLED','APPROVED_SHA','CONFIRMATION'})
        self.assertEqual(len(job['steps']), 3)
        for step in job['steps']:
            self.assertNotIn('continue-on-error', step)
        self.assertEqual(b.PAYLOAD, {'model':b.MODEL,'input':'Reply OK.','max_output_tokens':16,
                                    'tools':[],'store':False,'service_tier':'default','reasoning':{'effort':'none'}})


if __name__ == '__main__': unittest.main()
