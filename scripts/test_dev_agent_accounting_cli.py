"""Protected CLI tests: no network, no live credentials, no database."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dev_agent_accounting_cli import NoRedirect, main, read_envelope, write_result


class AccountingCliTests(unittest.TestCase):
    def test_duplicate_json_and_oversized_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"input.json"
            for text in ('{"payload":{},"payload":{}}','x'*65537):
                path.write_text(text)
                with self.assertRaises(ValueError):read_envelope(path)

    def test_result_private_and_exclusive(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"permit.json"
            write_result(path,{"test":"synthetic"})
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):write_result(path,{})
            self.assertEqual(json.loads(path.read_text()),{"test":"synthetic"})

    def test_redirects_never_forward_admin_credentials(self):
        with self.assertRaises(ValueError):NoRedirect().redirect_request(None,None,302,"",{},"https://example.invalid")

    def test_non_main_collector_denied_without_fetch_or_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/"result.json"
            with patch.dict(os.environ,{"GITHUB_REF":"refs/heads/untrusted"},clear=True),patch("dev_agent_accounting_cli.build_opener") as fetch:
                with contextlib.redirect_stderr(io.StringIO()):
                    code=main(["collect","--project-id","proj_acceptance_test","--output",str(output)])
                self.assertEqual(code,2);fetch.assert_not_called();self.assertFalse(output.exists())

    def test_missing_credentials_sanitized_no_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/"result.json";err=io.StringIO()
            with patch.dict(os.environ,{},clear=True),contextlib.redirect_stderr(err):
                code=main(["reserve","--project-id","proj_acceptance_test","--output",str(output)])
            self.assertEqual(code,2);self.assertFalse(output.exists())
            self.assertEqual(err.getvalue(),"Protected accounting command denied\n")

    def test_wrong_actual_workflow_identity_cannot_sign(self):
        env={"GITHUB_REF":"refs/heads/main","GITHUB_REPOSITORY":"mpeng98-source/Restaurant-AI-central",
             "GITHUB_SHA":"a"*40,"GITHUB_RUN_ID":"100","GITHUB_RUN_ATTEMPT":"1",
             "GITHUB_WORKFLOW_REF":"mpeng98-source/Restaurant-AI-central/.github/workflows/other.yml@refs/heads/main"}
        with patch.dict(os.environ,env,clear=True),patch("dev_agent_accounting_cli.build_opener") as fetch:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["collect","--project-id","proj_acceptance_test"]),2)
            fetch.assert_not_called()


if __name__=="__main__":
    unittest.main()
