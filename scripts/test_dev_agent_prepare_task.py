#!/usr/bin/env python3
import unittest
from dev_agent_prepare_task import prepare


def task(number, labels, title="Add inventory conversion test", body="Add a small Decimal test."):
    return {"number": number, "state": "open", "title": title,
            "body": body, "labels": [{"name": x} for x in labels]}


class PrepareTaskTests(unittest.TestCase):
    def test_selects_only_explicit_safe_task(self):
        p = {"issues": [task(2, ["agent-approved", "agent-safe"])], "pull_requests": []}
        self.assertEqual(prepare(p, 0)["number"], 2)

    def test_no_approved_task_skips_model(self):
        p = {"issues": [task(2, ["agent-approved"])], "pull_requests": []}
        self.assertFalse(prepare(p, 0)["selected"])

    def test_manual_issue_cannot_bypass_safe_label(self):
        p = {"issues": [task(2, ["agent-approved"])], "pull_requests": []}
        self.assertFalse(prepare(p, 2)["selected"])

    def test_manual_issue_cannot_bypass_block(self):
        p = {"issues": [task(2, ["agent-approved", "agent-safe", "agent-blocked"])], "pull_requests": []}
        self.assertFalse(prepare(p, 2)["selected"])

    def test_high_risk_issue_rejected(self):
        p = {"issues": [task(2, ["agent-approved", "agent-safe"], title="Change RLS permissions")], "pull_requests": []}
        self.assertFalse(prepare(p, 2)["selected"])

    def test_existing_draft_prevents_repeat(self):
        p = {"issues": [task(2, ["agent-approved", "agent-safe"])],
             "pull_requests": [{"state": "open", "title": "Agent proposal: issue #2"}]}
        self.assertFalse(prepare(p, 0)["selected"])

    def test_duplicate_issue_numbers_fail_closed(self):
        i = task(2, ["agent-approved", "agent-safe"])
        with self.assertRaises(ValueError):
            prepare({"issues": [i, i], "pull_requests": []}, 2)


if __name__ == "__main__":
    unittest.main()
