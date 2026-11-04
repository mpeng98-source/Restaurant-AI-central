import unittest
from unittest.mock import MagicMock
from dev_agent_neon_verify import verify


class NeonVerifyTests(unittest.TestCase):
    def make_connection(self, identity=("dev_agent_control_db", "dev_agent_runner"),
                        tables=None, schema=(True, False), grants=True):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [identity, schema] + [(grants,)] * 5
        cursor.fetchall.return_value = [(x,) for x in (tables or
            ["daily_budget", "run_reservation", "cost_observation", "run_usage", "alert_outbox"])]
        connection = MagicMock()
        connection.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor
        connect = MagicMock(return_value=connection)
        return connect

    def test_read_only_role_passes(self):
        verify(self.make_connection(), "postgresql://example.invalid/db")

    def test_admin_role_denied(self):
        with self.assertRaises(ValueError):
            verify(self.make_connection(identity=("dev_agent_control_db", "neondb_owner")),
                   "postgresql://example.invalid/db")

    def test_missing_table_denied(self):
        with self.assertRaises(ValueError):
            verify(self.make_connection(tables=["daily_budget"]), "postgresql://example.invalid/db")

    def test_create_privilege_denied(self):
        with self.assertRaises(ValueError):
            verify(self.make_connection(schema=(True, True)), "postgresql://example.invalid/db")

    def test_missing_select_denied(self):
        with self.assertRaises(ValueError):
            verify(self.make_connection(grants=False), "postgresql://example.invalid/db")


if __name__ == "__main__":
    unittest.main()
