import unittest
from dev_agent_queue import select_task
from dev_agent_reliability import budget_preflight, triage


def issue(n, state="OPEN"):
    return {"number": n, "state": state, "title": "Inventory Decimal test",
            "body": "Add a small conversion test.",
            "labels": [{"name": "agent-approved"}, {"name": "agent-safe"}]}


class ReliabilityTests(unittest.TestCase):
    def test_closed_merged_issue_is_not_reprocessed(self):
        self.assertFalse(select_task({"issues": [issue(24, "CLOSED")], "pull_requests": []}, 24)["selected"])

    def test_existing_open_draft_is_not_reprocessed(self):
        data = {"issues": [issue(27)], "pull_requests": [
            {"title": "Agent proposal: issue #27", "state": "OPEN"}]}
        self.assertFalse(select_task(data, 27)["selected"])

    def test_ci_failure_requires_human(self):
        self.assertEqual(triage([{"name": "backend", "status": "completed",
                                  "conclusion": "failure"}])["state"], "failed")

    def test_pending_ci_is_not_passed(self):
        self.assertEqual(triage([{"name": "backend", "status": "in_progress",
                                  "conclusion": None}])["state"], "pending")

    def test_unknown_ci_fails_closed(self):
        self.assertEqual(triage([{"name": "backend", "status": "completed",
                                  "conclusion": "skipped"}])["state"], "unknown")

    def test_all_successful_jobs(self):
        self.assertEqual(triage([{"name": "backend", "status": "completed",
                                  "conclusion": "success"}])["state"], "passed")

    def test_missing_jobs_unknown(self):
        self.assertEqual(triage([])["state"], "unknown")

    def test_budget_allows_bounded_run(self):
        self.assertTrue(budget_preflight("10", "2", "3", 1, 3)["allowed"])

    def test_budget_blocks_excess(self):
        self.assertFalse(budget_preflight("10", "4", "7", 1, 3)["allowed"])

    def test_budget_blocks_run_count(self):
        self.assertFalse(budget_preflight("10", "2", "1", 3, 3)["allowed"])

    def test_budget_rejects_nan(self):
        self.assertFalse(budget_preflight("NaN", "2", "1", 1, 3)["allowed"])

    def test_budget_rejects_missing_estimate(self):
        self.assertFalse(budget_preflight("10", "0", "1", 1, 3)["allowed"])


if __name__ == "__main__":
    unittest.main()
