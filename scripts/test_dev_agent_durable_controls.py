import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from dev_agent_durable_controls import reserve, queue_alert, deliver_one_alert


class FakeCursor:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.statements = []
    def execute(self, sql, params=None):
        self.statements.append((sql, params))
    def fetchone(self):
        return next(self.rows)

class FakeConnection:
    def __init__(self, rows):
        self.cur = FakeCursor(rows)
        self.transaction_calls = 0
    def transaction(self):
        conn = self
        class Transaction:
            def __enter__(self):
                conn.transaction_calls += 1
            def __exit__(self, *args):
                return False
        return Transaction()
    def cursor(self):
        cur = self.cur
        class Context:
            def __enter__(self):
                return cur
            def __exit__(self, *args):
                return False
        return Context()


class DurableTests(unittest.TestCase):
    def test_atomic_reservation(self):
        now = datetime(2026, 11, 4, tzinfo=timezone.utc)
        conn = FakeConnection([("0", "0", now), None, (0,)])
        result = reserve(conn, run_id=123, issue_number=24, project_id="proj_agent", now=now)
        self.assertTrue(result["allowed"])
        self.assertEqual(conn.transaction_calls, 1)
        self.assertTrue(any("FOR UPDATE" in q for q, _ in conn.cur.statements))
        self.assertTrue(any("INSERT INTO dev_agent_control.run_reservation" in q for q, _ in conn.cur.statements))

    def test_stale_cost_blocks_before_reservation(self):
        now = datetime(2026, 11, 4, tzinfo=timezone.utc)
        conn = FakeConnection([("0", "0", now-timedelta(hours=2))])
        self.assertFalse(reserve(conn, run_id=123, issue_number=24, project_id="proj_agent", now=now)["allowed"])
        self.assertFalse(any("INSERT INTO dev_agent_control.run_reservation" in q for q, _ in conn.cur.statements))

    def test_reserved_budget_blocks(self):
        now = datetime(2026, 11, 4, tzinfo=timezone.utc)
        conn = FakeConnection([("5", "1", now), None, (1,)])
        self.assertEqual(reserve(conn, run_id=123, issue_number=24, project_id="proj_agent", now=now)["reason"], "budget reservation exceeded")

    def test_existing_run_blocks_duplicate(self):
        now = datetime(2026, 11, 4, tzinfo=timezone.utc)
        conn = FakeConnection([("0", "0", now), (24,)])
        self.assertFalse(reserve(conn, run_id=123, issue_number=24, project_id="proj_agent", now=now)["allowed"])

    def test_alert_outbox_deduplicates(self):
        conn = FakeConnection([None])
        self.assertFalse(queue_alert(conn, alert_key="run-123-failed", run_id=123, code="CODEX_RUN_FAILED"))

    def test_alert_rejects_unapproved_code(self):
        with self.assertRaises(ValueError):
            queue_alert(FakeConnection([]), alert_key="x", run_id=123, code="SEND_RAW_LOGS")

    @patch("dev_agent_durable_controls.subprocess.run")
    def test_real_notification_transport_is_sanitized(self, runner):
        runner.return_value.stdout = "https://github.com/owner/repo/issues/42\n"
        conn = FakeConnection([("run-123-failed", 123, "CODEX_RUN_FAILED")])
        result = deliver_one_alert(conn, repo="owner/repo")
        self.assertEqual(result["issue_number"], 42)
        args = runner.call_args.args[0]
        self.assertEqual(args[:3], ["gh", "issue", "create"])
        self.assertNotIn("secret", " ".join(args).lower())
        self.assertTrue(any("state='sent'" in q for q, _ in conn.cur.statements))

    @patch("dev_agent_durable_controls.subprocess.run")
    def test_no_pending_alert_sends_nothing(self, runner):
        self.assertEqual(deliver_one_alert(FakeConnection([None]), repo="owner/repo")["status"], "empty")
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
