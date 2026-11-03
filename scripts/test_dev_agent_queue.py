#!/usr/bin/env python3
import unittest
from dev_agent_queue import select_task

def issue(n, labels=None, title="Add inventory unit conversion test", body="Add a Decimal test."):
    return {"number": n, "state": "OPEN", "title": title, "body": body,
            "labels": [{"name": x} for x in (labels or ["agent-approved", "agent-safe"])]}

class QueueTests(unittest.TestCase):
    def test_oldest_safe_issue(self):
        p = {"issues": [issue(23), issue(21)], "pull_requests": []}
        self.assertEqual(select_task(p)["number"], 21)

    def test_unapproved_issue_is_not_selected(self):
        p = {"issues": [issue(1, ["agent-safe"])], "pull_requests": []}
        self.assertFalse(select_task(p)["selected"])

    def test_human_only_and_blocked_are_rejected(self):
        for label in ("agent-needs-human", "agent-blocked"):
            p = {"issues": [issue(1, ["agent-approved", "agent-safe", label])], "pull_requests": []}
            self.assertFalse(select_task(p)["selected"])

    def test_existing_open_draft_prevents_duplicate(self):
        p = {"issues": [issue(4), issue(5)],
             "pull_requests": [{"title": "Agent proposal: issue #4", "state": "OPEN"}]}
        self.assertEqual(select_task(p)["number"], 5)

    def test_high_risk_task_requires_human(self):
        for word in ("RLS", "migration", "production", "credential", "credentials", "secret", "secrets", "authorization"):
            p = {"issues": [issue(1, title=f"Change {word}")], "pull_requests": []}
            self.assertFalse(select_task(p)["selected"], word)

    def test_requested_issue_must_be_eligible(self):
        p = {"issues": [issue(1, ["agent-safe"]), issue(2)], "pull_requests": []}
        self.assertFalse(select_task(p, 1)["selected"])
        self.assertEqual(select_task(p, 2)["number"], 2)

    def test_closed_issue_not_selected(self):
        item = issue(3)
        item["state"] = "CLOSED"
        self.assertFalse(select_task({"issues": [item], "pull_requests": []})["selected"])

    def test_oversized_issue_rejected(self):
        p = {"issues": [issue(3, body="a" * 12001)], "pull_requests": []}
        self.assertFalse(select_task(p)["selected"])

    def test_invalid_payload_fails_closed(self):
        with self.assertRaises(ValueError):
            select_task({"issues": {}, "pull_requests": []})

if __name__ == "__main__":
    unittest.main()
