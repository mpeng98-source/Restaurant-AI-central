"""Offline only: no credentials, GitHub writes or model requests."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import yaml
import dev_agent_bootstrap_runtime_diagnostic as d

SHA = 'a' * 40
ENV = {'GITHUB_REPOSITORY': d.REPOSITORY, 'GITHUB_EVENT_NAME': 'workflow_dispatch',
       'GITHUB_REF': 'refs/heads/main', 'GITHUB_WORKFLOW_REF': d.REPOSITORY+'/'+d.WORKFLOW+'@refs/heads/main',
       'GITHUB_SHA': SHA, 'WORKFLOW_SHA': SHA, 'APPROVED_SHA': SHA,
       'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_RUN_ID': '123', 'GITHUB_ACTOR': 'owner',
       'GH_TOKEN': 'synthetic-runtime-token'}
SETTINGS = {'name': d.ENVIRONMENT, 'can_admins_bypass': False,
            'protection_rules': [{'type': 'required_reviewers', 'prevent_self_review': True,
                                  'reviewers': [{'type':'User', 'reviewer': {'login':'independent'}}]},
                                 {'type':'branch_policy'}],
            'deployment_branch_policy': {'protected_branches':False, 'custom_branch_policies':True}}
POLICIES = {'total_count':1, 'branch_policies':[{'name':'main', 'type':'branch'}]}
RULESET = {'id': d.RULESET_ID, 'target':'tag', 'source_type':'Repository', 'source':d.REPOSITORY,
           'enforcement':'active', 'bypass_actors':[],
           'conditions':{'ref_name':{'include':[d.REF], 'exclude':[]}},
           'rules':[{'type':'update'}, {'type':'deletion'}]}


class FakeTransport:
    def __init__(self):
        self.values = copy.deepcopy({d.PATHS['main']: {'object':{'sha':SHA}},
                                     d.PATHS['environment']: SETTINGS,
                                     d.PATHS['branch_policy']: POLICIES,
                                     d.PATHS['ruleset']:RULESET})
        self.calls = []

    def get(self, path, token):
        self.calls.append(path)
        assert path in d.PATHS.values()
        assert token == ENV['GH_TOKEN']
        value = self.values[path]
        if isinstance(value, Exception):
            raise value
        return value


class DiagnosticTests(unittest.TestCase):
    def denied(self, transport, stage, status=None):
        result = d.diagnose(transport, ENV)
        self.assertNotEqual(result[stage], 'PASS')
        if status:
            self.assertEqual(result[stage], status)
        return result

    def test_complete_snapshot_passes_with_only_fixed_get_paths(self):
        t = FakeTransport()
        self.assertTrue(all(v == 'PASS' for v in d.diagnose(t, ENV).values()))
        self.assertEqual(t.calls, [d.PATHS[k] for k in ('main','environment','branch_policy','ruleset','main')])

    def test_missing_bypass_is_unknown_not_empty(self):
        t = FakeTransport(); del t.values[d.PATHS['ruleset']]['bypass_actors']
        self.denied(t, 'ruleset', 'UNKNOWN')

    def test_nonempty_or_malformed_bypass_denies(self):
        for bypass in ([{'actor_id':1}], None, {}, '', False):
            t = FakeTransport(); t.values[d.PATHS['ruleset']]['bypass_actors'] = bypass
            self.denied(t, 'ruleset')

    def test_http_403_404_and_timeout_at_every_endpoint(self):
        for stage, path in d.PATHS.items():
            for code in (403,404):
                t = FakeTransport()
                t.values[path] = HTTPError('https://private.invalid',code,'private',{},None)
                self.denied(t, stage, 'FAIL' if code == 404 else 'UNKNOWN')
            t = FakeTransport(); t.values[path] = TimeoutError('private')
            self.denied(t, stage, 'UNKNOWN')

    def test_environment_protections_are_mandatory(self):
        cases = [{'can_admins_bypass':True}, {'can_admins_bypass':None},
                 {'protection_rules':[]}, {'protection_rules':None},
                 {'protection_rules':[{'type':'required_reviewers','prevent_self_review':False,'reviewers':[1]}]},
                 {'protection_rules':[{'type':'required_reviewers','prevent_self_review':True,'reviewers':[]}]},
                 {'protection_rules':[{'type':'required_reviewers','prevent_self_review':True,
                                       'reviewers':[{'type':'User','reviewer':{'login':''}}]}]},
                 {'protection_rules':[{'type':'required_reviewers','prevent_self_review':True,
                                       'reviewers':[{'type':'User','reviewer':{'login':'OWNER'}}]}]},
                 {'deployment_branch_policy':None},
                 {'deployment_branch_policy':{'protected_branches':True,'custom_branch_policies':False}},
                 {'name':'other'}]
        for change in cases:
            t = FakeTransport(); t.values[d.PATHS['environment']].update(change)
            self.denied(t, 'environment')
        for key in SETTINGS:
            t = FakeTransport(); del t.values[d.PATHS['environment']][key]
            self.denied(t, 'environment')

    def test_wrong_branch_or_extra_policy_denies(self):
        for value in ({'total_count':2,'branch_policies':POLICIES['branch_policies']},
                      {'total_count':1,'branch_policies':[{'name':'*','type':'branch'}]},
                      {'total_count':1,'branch_policies':[{'name':'main','type':'tag'}]},
                      {'total_count':True,'branch_policies':POLICIES['branch_policies']}):
            t = FakeTransport(); t.values[d.PATHS['branch_policy']] = value
            self.denied(t, 'branch_policy')

    def test_exact_ruleset_identity_ref_and_restrictions_required(self):
        for change in ({'id':1}, {'id':True}, {'target':'branch'}, {'source':'attacker/repo'},
                       {'source_type':'Organization'}, {'enforcement':'evaluate'},
                       {'rules':[{'type':'deletion'}]},
                       {'conditions':{'ref_name':{'include':['refs/tags/*'],'exclude':[]}}},
                       {'conditions':{'ref_name':{'include':[d.REF],'exclude':[d.REF]}}},
                       {'conditions':{'ref_name':{'include':[d.REF,'refs/tags/other'],'exclude':[]}}}):
            t = FakeTransport(); t.values[d.PATHS['ruleset']].update(change)
            self.denied(t, 'ruleset')

    def test_wrong_context_or_workflow_sha_denies_before_network(self):
        for key, value in {'GITHUB_REPOSITORY':'attacker/repo', 'GITHUB_EVENT_NAME':'push',
                           'GITHUB_REF':'refs/heads/feature', 'GITHUB_WORKFLOW_REF':'forged',
                           'GITHUB_SHA':'bad', 'WORKFLOW_SHA':'b'*40, 'APPROVED_SHA':'b'*40,
                           'GITHUB_RUN_ATTEMPT':'2', 'GITHUB_RUN_ID':'0', 'GH_TOKEN':'',
                           'GITHUB_ACTOR':''}.items():
            t = FakeTransport()
            self.assertEqual(d.diagnose(t, {**ENV,key:value}), {'context':'FAIL'})
            self.assertEqual(t.calls, [])

    def test_main_movement_denies(self):
        t = FakeTransport(); original = t.get
        def get(path, token):
            value = original(path, token)
            if len(t.calls) == 5:
                return {'object':{'sha':'b'*40}}
            return value
        t.get = get
        self.denied(t, 'main_after', 'FAIL')

    def test_unexpected_response_types_fail_closed(self):
        for stage, path in d.PATHS.items():
            for value in (None, [], {}, 'private-body', 1):
                t = FakeTransport(); t.values[path] = value
                self.denied(t, stage, 'UNKNOWN')

    def test_output_never_contains_tokens_bodies_urls_or_errors(self):
        for error in (TimeoutError('PRIVATE-'+ENV['GH_TOKEN']),
                      HTTPError('https://private.invalid',403,'PRIVATE',{'Authorization':ENV['GH_TOKEN']},None),
                      ValueError('PRIVATE-response-body')):
            t = FakeTransport(); t.values[d.PATHS['ruleset']] = error
            out, err = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, ENV, clear=True), patch.object(d,'Transport',return_value=t), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(d.main(), 2)
            for value in ('PRIVATE', 'https://', ENV['GH_TOKEN'], 'Authorization'):
                self.assertNotIn(value, out.getvalue()+err.getvalue())
            self.assertIn('overall: DENIED', out.getvalue())

    def test_transport_has_no_mutation_or_arbitrary_endpoint_interface(self):
        t = d.Transport(); opener = MagicMock(); t.opener = opener
        opener.open.return_value.__enter__.return_value.read.return_value = b'{}'
        for path in d.PATHS.values():
            self.assertEqual(t.get(path, 'synthetic'), {})
            request = opener.open.call_args.args[0]
            self.assertEqual(request.get_method(), 'GET')
            self.assertIsNone(request.data)
            self.assertEqual(request.full_url,d.BASE+path)
        for path in ('git/refs', 'git/tags', '../rulesets/1', 'https://api.openai.com/v1/responses'):
            before = opener.open.call_count
            with self.assertRaises(d.Failed): t.get(path,'synthetic')
            self.assertEqual(opener.open.call_count,before)
        self.assertFalse(hasattr(t, 'request'))
        with self.assertRaises(d.Unknown): d.NoRedirect().redirect_request(None)

    def test_transport_timeout_invalid_json_and_oversize_never_retry(self):
        t = d.Transport(); opener = MagicMock(); t.opener = opener
        opener.open.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError): t.get(d.PATHS['ruleset'],'synthetic')
        opener.open.assert_called_once()
        opener.open.side_effect = None
        for raw in (b'not json', b'x'*65537):
            opener.open.reset_mock()
            opener.open.return_value.__enter__.return_value.read.return_value = raw
            with self.assertRaises((ValueError,d.Unknown)): t.get(d.PATHS['ruleset'],'synthetic')
            opener.open.assert_called_once()

    def test_workflow_manual_protected_and_secrets_isolated(self):
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.load((root/d.WORKFLOW).read_text(),Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow['on']),{'workflow_dispatch'})
        self.assertEqual(workflow['permissions'],{'contents':'read'})
        self.assertEqual(set(workflow['jobs']),{'diagnostic'})
        job = workflow['jobs']['diagnostic']
        self.assertEqual(job['permissions'],{'contents':'write','actions':'read'})
        self.assertEqual(job['environment'],d.ENVIRONMENT)
        for text in ("github.ref == 'refs/heads/main'", "github.run_attempt == 1", "github.event_name == 'workflow_dispatch'"):
            self.assertIn(text,job['if'])
        self.assertEqual(workflow['concurrency'],{'group':'chubby-protected-coding-agent','cancel-in-progress':'false'})
        self.assertEqual(job['steps'][0]['with'],{'ref':'${{ github.sha }}','persist-credentials':'false'})
        self.assertEqual(len(job['steps']),3)
        final = job['steps'][-1]
        self.assertEqual(final['run'],'python scripts/dev_agent_bootstrap_runtime_diagnostic.py')
        self.assertEqual(final['env'],{'GH_TOKEN':'${{ github.token }}','APPROVED_SHA':'${{ inputs.approved_sha }}','WORKFLOW_SHA':'${{ github.workflow_sha }}'})
        self.assertNotIn('secrets.',(root/d.WORKFLOW).read_text())
        for step in job['steps']:
            self.assertNotIn('continue-on-error',step)
        bootstrap = yaml.load((root/'.github/workflows/dev-agent-bootstrap.yml').read_text(),Loader=yaml.BaseLoader)
        self.assertEqual(job['permissions'],bootstrap['jobs']['bootstrap']['permissions'])


if __name__ == '__main__':
    unittest.main()
