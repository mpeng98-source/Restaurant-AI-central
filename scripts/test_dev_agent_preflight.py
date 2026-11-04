import json
import os
import tempfile
import unittest
from unittest.mock import patch
from dev_agent_preflight import main


class PreflightTests(unittest.TestCase):
    def test_missing_control_plane_credential_denies(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {}, clear=True):
            out = d + "/permit.json"
            with patch("sys.argv", ["preflight", "--run-id", "123", "--issue", "24",
                                    "--project-id", "proj_agent", "--output", out]):
                self.assertEqual(main(), 2)
            self.assertFalse(os.path.exists(out))

    def test_invalid_run_denies(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(
                os.environ, {"DEV_AGENT_CONTROL_DATABASE_URL": "postgresql://invalid"}, clear=True):
            out = d + "/permit.json"
            with patch("sys.argv", ["preflight", "--run-id", "0", "--issue", "24",
                                    "--project-id", "proj_agent", "--output", out]):
                self.assertEqual(main(), 2)
            self.assertFalse(os.path.exists(out))

    def test_unreachable_database_denies_without_permit(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(
                os.environ, {"DEV_AGENT_CONTROL_DATABASE_URL": "postgresql://invalid:invalid@127.0.0.1:1/invalid"}, clear=True):
            out = d + "/permit.json"
            with patch("sys.argv", ["preflight", "--run-id", "123", "--issue", "24",
                                    "--project-id", "proj_agent", "--output", out]):
                self.assertEqual(main(), 2)
            self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
