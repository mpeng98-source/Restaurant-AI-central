import json
from pathlib import Path
import tempfile
import unittest
import yaml
from artifact import persist

HERE=Path(__file__).resolve().parent


class ArtifactTests(unittest.TestCase):
    def record(self):
        return dict(mode='issue-58-unknown-cost-once-v1',prior_cost_state='unknown',
            request_ceiling_usd='5.000000',claim_consumed=True,run_id=123,
            head_sha='a'*40,task_digest='b'*64,request_digest='c'*64,settled=False)

    def test_failure_evidence_is_private_exclusive_and_unknown(self):
        with tempfile.TemporaryDirectory() as path:
            target=persist(json.dumps(self.record()),path,run_id=123,head='a'*40)
            self.assertEqual(target.stat().st_mode & 0o777,0o600)
            self.assertEqual(json.loads(target.read_text()),self.record())
            # Subsequent generator failure cannot convert this into settled/zero.
            with self.assertRaises(FileExistsError):
                persist(json.dumps(self.record()),path,run_id=123,head='a'*40)

    def test_raw_secrets_wrong_run_and_zero_claims_never_written(self):
        for changes in ({'key':'synthetic-key'},{'run_id':124},{'run_id':True},
                        {'prior_cost_state':'zero'},{'settled':True},{'head_sha':'e'*40}):
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as path:
                record=self.record();record.update(changes)
                with self.assertRaises(ValueError):
                    persist(json.dumps(record),path,run_id=123,head='a'*40)
                self.assertEqual(list(Path(path).iterdir()),[])

    def test_duplicate_and_oversized_metadata_rejected(self):
        with tempfile.TemporaryDirectory() as path:
            for raw in ('{"mode":"x","mode":"y"}',' '*2049):
                with self.assertRaises(ValueError):persist(raw,path,run_id=123,head='a'*40)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.w=yaml.safe_load((HERE/'workflow.candidate.yml').read_text())

    def test_all_protected_environments_and_general_hold_retained(self):
        expected={'approval':'dev-agent-run-approval-v27','audit':'dev-agent-control-audit-v27',
            'collect':'cost-audit','ingest':'cost-writer-v27','reserve':'dev-agent-reserver-v27',
            'authorize':'dev-agent-verifier-v27','generate':'dev-agent-codex-v27',
            'publish':'dev-agent-publisher-v27','record_failure':'dev-agent-failure-v27'}
        for job,environment in expected.items():
            self.assertEqual(self.w['jobs'][job]['environment'],environment)
        self.assertEqual(self.w['jobs']['publish']['if'],'${{ false }}')
        approval=str(self.w['jobs']['approval'])
        self.assertIn('github.run_attempt == 1',approval)
        self.assertIn('refs/heads/main',approval)
        self.assertIn('test "$REQUESTED_ISSUE" = "58"',approval)

    def test_exception_never_reaches_cost_or_normal_reservation(self):
        for job in ('collect','ingest','reserve'):
            for step in self.w['jobs'][job]['steps']:
                if step.get('name')=='Record explicit unknown-cost exception barrier':continue
                self.assertEqual(step['if'],'${{ !inputs.unknown_cost_exception }}')
        authorize=self.w['jobs']['authorize']
        normal=next(s for s in authorize['steps'] if s.get('id')=='authorize')
        self.assertEqual(normal['if'],'${{ !inputs.unknown_cost_exception }}')

    def test_credentials_separated_and_artifacts_exact(self):
        jobs=self.w['jobs']
        self.assertNotIn('OPENAI_API_KEY',str(jobs['authorize']))
        self.assertNotIn('DATABASE_URL',str(jobs['generate']))
        self.assertNotIn('PERMIT_HMAC_KEY',str(jobs['generate']))
        for job in ('authorize','generate'):
            upload=next(s for s in jobs[job]['steps'] if s.get('uses','').startswith('actions/upload-artifact@'))
            self.assertIn('always()',upload['if'])
            self.assertEqual(upload['with']['retention-days'],7)
            self.assertEqual(upload['with']['if-no-files-found'],'error')
            paths=upload['with']['path'].splitlines()
            self.assertTrue(set(paths)<= {'${{ runner.temp }}/scoped-canary-exception.json',
                                        '${{ runner.temp }}/scoped-canary-result.json'})


if __name__=='__main__':unittest.main()
