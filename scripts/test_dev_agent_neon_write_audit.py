import unittest
from unittest.mock import MagicMock
from dev_agent_neon_write_audit import run

class NeonWriteAuditTests(unittest.TestCase):
    def test_missing_url_fails_closed(self):
        connect = MagicMock()
        with self.assertRaises(ValueError):
            run(connect, MagicMock(), "")
        connect.assert_not_called()

    def test_connection_error_does_not_succeed(self):
        connect = MagicMock(side_effect=RuntimeError("unavailable"))
        with self.assertRaises(RuntimeError):
            run(connect, MagicMock(), "postgresql://example.invalid/db")

if __name__ == "__main__":
    unittest.main()
