#!/usr/bin/env python3
import json
import subprocess
import unittest
from unittest.mock import patch
from dev_agent_snapshot import fetch_pages, snapshot


def response(pages):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(pages), stderr="")


class SnapshotTests(unittest.TestCase):
    @patch("dev_agent_snapshot.subprocess.run")
    def test_pagination_and_pr_exclusion(self, run):
        run.side_effect = [
            response([[{"number": 1, "state": "open", "title": "Task", "body": "x", "labels": []}],
                      [{"number": 2, "state": "open", "title": "PR as issue", "labels": [], "pull_request": {}}]]),
            response([[{"number": 2, "state": "open", "title": "Agent proposal: issue #1"}]])
        ]
        result = snapshot("owner/repo")
        self.assertEqual([x["number"] for x in result["issues"]], [1])
        self.assertEqual([x["number"] for x in result["pull_requests"]], [2])
        self.assertEqual(run.call_count, 2)
        self.assertTrue(all(call.kwargs["timeout"] == 90 for call in run.call_args_list))

    @patch("dev_agent_snapshot.subprocess.run")
    def test_api_failure(self, run):
        run.side_effect = subprocess.CalledProcessError(1, ["gh", "api"])
        with self.assertRaises(subprocess.CalledProcessError):
            snapshot("owner/repo")

    @patch("dev_agent_snapshot.subprocess.run")
    def test_malformed_page(self, run):
        run.return_value = response([{"not": "a page"}])
        with self.assertRaises(ValueError):
            fetch_pages("owner/repo", "issues")

    @patch("dev_agent_snapshot.subprocess.run")
    def test_rejects_oversized_page(self, run):
        run.return_value = response([[{}] * 101])
        with self.assertRaises(ValueError):
            fetch_pages("owner/repo", "issues")

    @patch("dev_agent_snapshot.subprocess.run")
    def test_invalid_repo_never_calls_gh(self, run):
        for name in ("../bad", "owner/..", "./repo", "owner/-repo", "owner/repo/extra"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                fetch_pages(name, "issues")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
