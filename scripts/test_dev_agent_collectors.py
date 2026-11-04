import json
import subprocess
import unittest
from unittest.mock import patch
from dev_agent_ci_collector import collect
from dev_agent_openai_costs import sum_project_costs


class CollectorTests(unittest.TestCase):
    @patch("dev_agent_ci_collector.subprocess.run")
    def test_ci_collects_only_metadata(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps([
            {"jobs": [{"name": "backend", "status": "completed", "conclusion": "failure",
                       "steps": [{"name": "sensitive", "output": "not for report"}]}]}
        ]), "")
        self.assertEqual(collect("owner/repo", 123)["jobs"], [
            {"name": "backend", "status": "completed", "conclusion": "failure"}])

    @patch("dev_agent_ci_collector.subprocess.run")
    def test_ci_api_failure(self, run):
        run.side_effect = subprocess.CalledProcessError(1, ["gh", "api"])
        with self.assertRaises(subprocess.CalledProcessError):
            collect("owner/repo", 123)

    @patch("dev_agent_ci_collector.subprocess.run")
    def test_ci_malformed_response(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps([{"wrong": []}]), "")
        with self.assertRaises(ValueError):
            collect("owner/repo", 123)

    @patch("dev_agent_ci_collector.subprocess.run")
    def test_ci_rejects_invalid_repo(self, run):
        with self.assertRaises(ValueError):
            collect("../bad", 123)
        run.assert_not_called()

    def test_costs_project_filter_and_pagination(self):
        urls = []
        pages = [
            {"data": [{"results": [
                {"project_id": "proj_agent", "amount": {"value": 1.25, "currency": "usd"}},
                {"project_id": "proj_other", "amount": {"value": 99, "currency": "usd"}}]}],
             "next_page": "next"},
            {"data": [{"results": [
                {"project_id": "proj_agent", "amount": {"value": 0.75, "currency": "usd"}}]}],
             "next_page": None}
        ]
        def fetch(url):
            urls.append(url)
            return pages[len(urls) - 1]
        result = sum_project_costs(fetch, 1000, 2000, "proj_agent")
        self.assertEqual(result["reported_cost_usd"], "2.00")
        self.assertIn("page=next", urls[1])

    def test_costs_rejects_malformed_currency(self):
        def fetch(_):
            return {"data": [{"results": [
                {"project_id": "proj_agent", "amount": {"value": 1, "currency": "eur"}}]}]}
        with self.assertRaises(ValueError):
            sum_project_costs(fetch, 1000, 2000, "proj_agent")

    def test_costs_rejects_repeated_cursor(self):
        def fetch(_):
            return {"data": [], "next_page": "again"}
        with self.assertRaises(ValueError):
            sum_project_costs(fetch, 1000, 2000, "proj_agent")

    def test_costs_rejects_invalid_interval(self):
        with self.assertRaises(ValueError):
            sum_project_costs(lambda _: {}, 2000, 1000, "proj_agent")


if __name__ == "__main__":
    unittest.main()
