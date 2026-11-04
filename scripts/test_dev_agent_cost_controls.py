import unittest
from dev_agent_cost_controls import reconcile, quota_preflight, alert_decision

RUN = {"run_id": 123, "project_id": "proj_agent", "status": "completed",
       "codex_invoked": True, "started_at": 1000, "ended_at": 1200}
BEFORE = {"project_id": "proj_agent", "source": "openai_organization_costs",
          "start_time": 0, "end_time": 2000, "observed_at": 1300,
          "reported_cost_usd": "1.20", "settlement_delay_possible": True}
AFTER = {**BEFORE, "observed_at": 1800, "reported_cost_usd": "1.75"}


class CostControlsTests(unittest.TestCase):
    def test_cost_delta_is_explicitly_not_per_run_charge(self):
        result = reconcile(RUN, BEFORE, AFTER)
        self.assertEqual(result["project_reported_delta_usd"], "0.55")
        self.assertFalse(result["exact_run_cost_known"])

    def test_mismatched_project_fails(self):
        with self.assertRaises(ValueError):
            reconcile(RUN, BEFORE, {**AFTER, "project_id": "proj_other"})

    def test_cost_decrease_fails(self):
        with self.assertRaises(ValueError):
            reconcile(RUN, BEFORE, {**AFTER, "reported_cost_usd": "0.01"})

    def test_stale_or_missing_observation_fails(self):
        args = self.args()
        args["observed_at"] = 1
        self.assertFalse(quota_preflight(**args)["allowed"])

    def test_quota_counts_reserved_and_failed_runs(self):
        args = self.args()
        args["history"] = [{"run_id": 1, "reserved_at": 100000, "state": "reserved"},
                           {"run_id": 2, "reserved_at": 100100, "state": "failed"}]
        args["max_daily_runs"] = 2
        self.assertEqual(quota_preflight(**args)["reason"], "daily run quota reached")

    def test_duplicate_records_fail_closed(self):
        args = self.args()
        args["history"] = [{"run_id": 1, "reserved_at": 100000, "state": "reserved"}] * 2
        self.assertFalse(quota_preflight(**args)["allowed"])

    def test_budget_rejects_estimate(self):
        args = self.args()
        args["reported_cost_usd"] = "9"
        args["estimated_max_run_usd"] = "2"
        self.assertFalse(quota_preflight(**args)["allowed"])

    def test_valid_preflight_requires_reservation(self):
        self.assertTrue(quota_preflight(**self.args())["allowed"])

    def test_alert_is_sanitized(self):
        result = alert_decision(ci_state="failed", budget_allowed=False,
                                cost_data_stale=True, run_failed=False)
        self.assertTrue(result["alert"])
        self.assertFalse(result["include_raw_logs"])
        self.assertEqual(len(result["codes"]), 3)

    @staticmethod
    def args():
        return {"now": 100200, "history": [], "max_daily_runs": 3,
                "daily_budget_usd": "10", "estimated_max_run_usd": "2",
                "reported_cost_usd": "1", "observed_at": 100100}


if __name__ == "__main__":
    unittest.main()
