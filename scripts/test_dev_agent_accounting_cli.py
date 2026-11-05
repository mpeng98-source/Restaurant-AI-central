"""Protected CLI tests: no network, no live credentials, no database."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import yaml

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


class CostDiagnosticTests(unittest.TestCase):
    now = 1793815200  # 2026-11-04 18:00 UTC
    workflow = ".github/workflows/dev-agent-cost-diagnostic.yml"
    env = {"GITHUB_REF": "refs/heads/main", "GITHUB_REPOSITORY": "mpeng98-source/Restaurant-AI-central",
           "GITHUB_SHA": "a"*40, "GITHUB_RUN_ID": "100", "GITHUB_RUN_ATTEMPT": "1",
           "GITHUB_WORKFLOW_REF": "mpeng98-source/Restaurant-AI-central/"+workflow+"@refs/heads/main",
           "OPENAI_ADMIN_KEY": "synthetic-admin-key-never-live"}

    def page(self, rows=True):
        start = self.now - 18*3600
        return {"data": [{"start_time": start, "end_time": start+86400, "results": [
            {"project_id": "proj_acceptance_test", "amount": {"currency": "usd", "value": "1.25"}}
        ] if rows else []}], "has_more": False, "next_page": None}

    def invoke(self, *, payload=None, error=None, env=None, extra=()):
        out, err = io.StringIO(), io.StringIO()
        transport = MagicMock()
        if error is not None:
            transport.open.side_effect = error
        else:
            transport.open.return_value.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        with patch.dict(os.environ, self.env if env is None else env, clear=True), \
                patch("dev_agent_accounting_cli.time.time", return_value=self.now), \
                patch("dev_agent_accounting_cli.build_opener", return_value=transport), \
                patch("dev_agent_accounting_cli.sign_cost") as signer, \
                patch("dev_agent_accounting_cli.write_result") as writer, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["diagnose-costs", "--project-id", "proj_acceptance_test",
                         "--utc-day", "2026-11-04", "--producer-workflow", self.workflow, *extra])
        signer.assert_not_called()
        writer.assert_not_called()
        self.assertNotIn(self.env["OPENAI_ADMIN_KEY"], out.getvalue()+err.getvalue())
        return code, out.getvalue(), err.getvalue(), transport

    def test_read_only_diagnostic_validates_real_collector_without_signing(self):
        code, out, err, transport = self.invoke(payload=self.page())
        self.assertEqual(code, 0)
        self.assertIn("no signed evidence or model invocation", out)
        self.assertEqual(err, "")
        transport.open.assert_called_once()

    def test_distinct_fixed_codes_never_emit_exception_url_or_body(self):
        secret = "synthetic-private-response-never-log"
        cases = [(HTTPError("https://example.invalid/"+secret, n, secret, {}, io.BytesIO(secret.encode())),
                  "COST_API_HTTP_"+str(n)) for n in (400, 401, 403, 429)]
        cases += [(HTTPError("https://example.invalid/"+secret, 503, secret, {}, None), "COST_API_HTTP_OTHER"),
                  (URLError(secret), "COST_API_TRANSPORT"), (TimeoutError(secret), "COST_API_TRANSPORT"),
                  (ValueError(secret), "COST_RESPONSE_INVALID")]
        for error, reason in cases:
            with self.subTest(reason=reason):
                code, out, err, _ = self.invoke(error=error)
                self.assertEqual((code, out), (2, ""))
                self.assertEqual(err, "Protected accounting command denied ["+reason+"]\n")
                self.assertNotIn(secret, err)

    def test_no_project_rows_remain_unknown_and_invalid_responses_stay_denied(self):
        for payload, reason in ((self.page(False), "COST_PROJECT_COSTS_UNKNOWN"),
                                ({"private": "synthetic-private-response"}, "COST_RESPONSE_INVALID")):
            with self.subTest(reason=reason):
                code, out, err, _ = self.invoke(payload=payload)
                self.assertEqual((code, out), (2, ""))
                self.assertEqual(err, "Protected accounting command denied ["+reason+"]\n")

    def test_normal_collector_still_requires_signing_and_emits_authenticated_evidence(self):
        for signing_key in (None, "synthetic-cost-signing-key-at-least-32-bytes"):
            with self.subTest(signing_configured=bool(signing_key)), tempfile.TemporaryDirectory() as folder:
                output = Path(folder)/"cost.json"
                env = dict(self.env)
                if signing_key:
                    env["DEV_AGENT_COST_SIGNING_KEY"] = signing_key
                transport = MagicMock()
                transport.open.return_value.__enter__.return_value.read.return_value = json.dumps(self.page()).encode()
                err = io.StringIO()
                with patch.dict(os.environ, env, clear=True), \
                        patch("dev_agent_accounting_cli.time.time", return_value=self.now), \
                        patch("dev_agent_accounting_cli.build_opener", return_value=transport), \
                        contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                    code = main(["collect", "--project-id", "proj_acceptance_test", "--utc-day", "2026-11-04",
                                 "--producer-workflow", self.workflow, "--output", str(output)])
                if signing_key:
                    self.assertEqual(code, 0)
                    evidence = json.loads(output.read_text())
                    self.assertEqual(set(evidence), {"payload", "signature"})
                    self.assertEqual(evidence["payload"]["report"]["reported_usd"], "1.250000")
                else:
                    self.assertEqual(code, 2)
                    self.assertFalse(output.exists())
                    self.assertEqual(err.getvalue(), "Protected accounting command denied [COST_SIGNING_DENIED]\n")

    def test_bad_context_configuration_and_artifact_request_fail_before_network(self):
        for env, extra, reason in (({**self.env, "GITHUB_REF": "refs/heads/untrusted"}, (), "COST_CONTEXT_INVALID"),
                ({**self.env, "GITHUB_WORKFLOW_REF": "untrusted/workflow"}, (), "COST_CONTEXT_INVALID"),
                ({**self.env, "OPENAI_ADMIN_KEY": ""}, (), "COST_CONFIGURATION_MISSING"),
                (self.env, ("--output", "/not-created-by-diagnostic.json"), "COST_CONFIGURATION_MISSING")):
            with self.subTest(reason=reason):
                code, out, err, transport = self.invoke(env=env, extra=extra)
                self.assertEqual((code, out), (2, ""))
                self.assertEqual(err, "Protected accounting command denied ["+reason+"]\n")
                transport.open.assert_not_called()

    def test_manual_diagnostic_workflow_has_only_protected_read_only_inputs(self):
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root/self.workflow).read_text())
        # PyYAML's YAML 1.1 loader reads the bare 'on' key as True.
        self.assertEqual(workflow.get("on", workflow.get(True)), {"workflow_dispatch": None})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        job = workflow["jobs"]["diagnose"]
        self.assertIn("github.ref == 'refs/heads/main'", job["if"])
        self.assertEqual(job["environment"], "cost-audit")
        self.assertEqual(len(job["steps"]), 3)
        step = job["steps"][-1]
        self.assertEqual(set(step["env"]), {"OPENAI_ADMIN_KEY", "PROJECT_ID"})
        self.assertIn(" diagnose-costs ", step["run"])
        self.assertNotIn("--output", step["run"])
        self.assertIn(self.workflow, step["run"])


if __name__=="__main__":
    unittest.main()
