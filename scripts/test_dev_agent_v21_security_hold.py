"""Policy-only CI checks: v2.1 must not invoke Codex until trusted permit gate lands.

Never runs workflows, fetches secrets, connects to Neon, or incurs API cost.
"""
from pathlib import Path
import unittest
import re

WF=Path(__file__).resolve().parents[1]/".github/workflows/chubby-dev-agent-v2-1.yml"

class FailClosedV21Tests(unittest.TestCase):
    def test_job_is_unconditionally_disabled(self):
        workflow=WF.read_text()
        self.assertRegex(workflow,r"(?m)^  develop:\s*\n(?:    #[^\n]*\n)*    if: \$\{\{ false \}\}")

    def test_codex_step_is_unconditionally_disabled(self):
        workflow=WF.read_text()
        self.assertRegex(workflow,r"(?m)^      - name: Run bounded Codex implementation\s*\n(?:        #[^\n]*\n)*        if: \$\{\{ false \}\}")

    def test_manual_issue_selection_remains_but_cannot_bypass_hold(self):
        workflow=WF.read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("issue_number:",workflow)
        self.assertIn("if: ${{ false }}", workflow)

if __name__ == "__main__":
    unittest.main()
