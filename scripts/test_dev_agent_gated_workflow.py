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
                    if (step.get('uses','').startswith('openai/codex-action@')
                            or step.get('run')=='python experiments/canary_candidate/run.py'):
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
        self.assertEqual(jobs['publish']['if'],'${{ false }}')
        self.assertNotIn('schedule',wf['on'])

    def test_general_coding_held_and_canary_explicitly_selected(self):
        import subprocess
        wf=read(ROOT/'.github/workflows/chubby-dev-agent-gated.yml');jobs=wf['jobs']
        approval=jobs['approval'];gate=approval['steps'][0]
        self.assertIn('github.run_attempt == 1',approval['if'])
        self.assertEqual(wf['on']['workflow_dispatch']['inputs']['scoped_canary']['default'],'false')
        self.assertEqual(gate['env'],{'SCOPED_CANARY':'${{ inputs.scoped_canary }}',
            'UNKNOWN_COST_EXCEPTION':'${{ inputs.unknown_cost_exception }}'})
        self.assertEqual(wf['on']['workflow_dispatch']['inputs']['unknown_cost_exception']['default'],'false')
        for issue,exception,expected in [('58','true',0),('59','true',1),('','true',1),('59','false',0)]:
            result=subprocess.run(['/bin/sh','-c',gate['run']],env={'SCOPED_CANARY':'true',
                'UNKNOWN_COST_EXCEPTION':exception,'REQUESTED_ISSUE':issue},capture_output=True)
            self.assertEqual(result.returncode,expected)
        for value,expected in [('',1),('false',1),('TRUE',1),('true',0)]:
            result=subprocess.run(['/bin/sh','-c',gate['run']],env={'SCOPED_CANARY':value},capture_output=True)
            self.assertEqual(result.returncode,expected)
        self.assertEqual(jobs['select']['needs'],'approval')
        self.assertEqual(jobs['publish']['if'],'${{ false }}')

    def test_canary_admitted_and_only_sanitized_evidence_follows(self):
        jobs=read(ROOT/'.github/workflows/chubby-dev-agent-gated.yml')['jobs']
        model=jobs['generate'];steps=model['steps']
        calls=[i for i,s in enumerate(steps) if s.get('run')=='python experiments/canary_candidate/run.py']
        self.assertEqual(len(calls),1);index=calls[0]
        self.assertEqual(steps[index]['env']['OPENAI_API_KEY'],'${{ secrets.CHUBBY_CODEX_OPENAI_API_KEY }}')
        self.assertEqual(steps[index]['env']['CANARY_MODE'],'synthetic-one-shot-v1')
        self.assertEqual(steps[index-1]['run'],'python scripts/dev_agent_gate_cli.py admit')
        self.assertEqual(len(steps[index+1:]),1)
        upload=steps[index+1]
        self.assertEqual(upload['uses'],'actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f')
        self.assertEqual(upload['if'],'${{ always() }}')
        self.assertEqual(upload['with']['path'].splitlines(),['${{ runner.temp }}/scoped-canary-result.json',
            '${{ runner.temp }}/scoped-canary-exception.json'])
        self.assertEqual(upload['with']['retention-days'],'7')
        self.assertEqual(upload['with']['if-no-files-found'],'error')
        rendered=yaml.dump(model)
        for key in ('DATABASE_URL','HMAC_KEY','COST_SIGNING_KEY','OPENAI_ADMIN_KEY','PR_TOKEN','PERMIT_JSON','openai/codex-action'):
            self.assertNotIn(key,rendered)
        for step in steps:self.assertNotEqual(step.get('continue-on-error'),'true')
        freshness=next(i for i,s in enumerate(steps) if s.get('run','').endswith('run.py --check-admission'))
        pull=next(i for i,s in enumerate(steps) if s.get('run','').startswith('docker pull '))
        self.assertLess(freshness,pull);self.assertLess(pull,index)

    def test_exact_reviewed_candidate_is_installed(self):
        self.assertEqual((ROOT/'.github/workflows/chubby-dev-agent-gated.yml').read_bytes(),
            (ROOT/'experiments/first_run_accounting/workflow.candidate.yml').read_bytes())

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
