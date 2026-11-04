"""Structural enforcement: all model entrypoints must traverse the gate DAG."""
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]


def read(path):return yaml.load(path.read_text(),Loader=yaml.BaseLoader)


class WorkflowBoundaryTests(unittest.TestCase):
    def test_only_one_model_entrypoint_and_no_schedule(self):
        found=[]
        for path in (ROOT/'.github/workflows').glob('*.yml'):
            wf=read(path)
            for job_id,job in wf.get('jobs',{}).items():
                for step in job.get('steps',[]):
                    if step.get('uses','').startswith('openai/codex-action@'):
                        found.append((path.name,job_id))
                        self.assertEqual(set(wf['on']),{'workflow_dispatch'})
        self.assertEqual(found,[('chubby-dev-agent-gated.yml','generate')])

    def test_graph_protects_model_and_publication(self):
        wf=read(ROOT/'.github/workflows/chubby-dev-agent-gated.yml');jobs=wf['jobs']
        expected={'select':['approval'],'audit':['select'],'collect':['audit'],'ingest':['collect'],
                  'reserve':['select','ingest'],'authorize':['select','reserve'],
                  'generate':['select','authorize'],'publish':['select','authorize','generate']}
        for name,needs in expected.items():
            actual=jobs[name]['needs'];actual=[actual] if isinstance(actual,str) else actual
            self.assertEqual(actual,needs)
        self.assertIn("vars.CHUBBY_DEV_AGENT_GATED_ENABLED == 'true'",jobs['approval']['if'])
        self.assertIn("refs/heads/main",jobs['approval']['if'])
        self.assertIn("needs.authorize.result == 'success'",jobs['generate']['if'])
        self.assertIn("needs.generate.result == 'success'",jobs['publish']['if'])
        self.assertNotIn('schedule',wf['on'])

    def test_v3_security_hold_precedes_collection_and_cannot_be_enabled_by_variable(self):
        jobs=read(ROOT/'.github/workflows/chubby-dev-agent-gated.yml')['jobs']
        approval=jobs['approval']
        self.assertIn('github.run_attempt == 1',approval['if'])
        self.assertIn('exit 1',approval['steps'][0]['run'])
        self.assertIn('spending bounds',approval['steps'][0]['run'])
        self.assertEqual(jobs['select']['needs'],'approval')

    def test_model_last_and_no_control_or_publication_secrets(self):
        jobs=read(ROOT/'.github/workflows/chubby-dev-agent-gated.yml')['jobs']
        model=jobs['generate'];last=model['steps'][-1]
        self.assertTrue(last['uses'].startswith('openai/codex-action@'))
        self.assertEqual(last['with']['safety-strategy'],'drop-sudo')
        self.assertEqual(last['with']['permission-profile'],':workspace')
        rendered=yaml.dump(model)
        for key in ('DATABASE_URL','HMAC_KEY','COST_SIGNING_KEY','OPENAI_ADMIN_KEY','PR_TOKEN','PERMIT_JSON'):
            self.assertNotIn(key,rendered)
        for step in model['steps']:
            self.assertNotEqual(step.get('continue-on-error'),'true')
        self.assertIn('dev_agent_gate_cli.py admit',model['steps'][-2]['run'])
        self.assertEqual(jobs['publish']['steps'][-1]['run'],'python scripts/dev_agent_proposal.py')

    def test_every_checkout_is_immutable_without_credentials(self):
        wf=read(ROOT/'.github/workflows/chubby-dev-agent-gated.yml')
        for job in wf['jobs'].values():
            self.assertEqual(job['runs-on'],'ubuntu-24.04')
            self.assertIn('environment',job) if job is not wf['jobs']['select'] else None
            for step in job['steps']:
                if step.get('uses','').startswith('actions/checkout@'):
                    self.assertEqual(step['with']['ref'],'${{ github.sha }}')
                    self.assertEqual(step['with']['persist-credentials'],'false')


if __name__=="__main__":unittest.main()
