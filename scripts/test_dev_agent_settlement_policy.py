import unittest
from datetime import datetime, timedelta, timezone
from dev_agent_utc_costs import collect_utc_day
from dev_agent_settlement_policy import assess, settlement_transition

NOW = datetime(2026, 11, 4, 18, tzinfo=timezone.utc)

class CostAndSettlementTests(unittest.TestCase):
    def test_utc_day_not_rolling_24h(self):
        urls = []
        def fetch(url):
            urls.append(url)
            return {"data": [{"results": [{"project_id": "proj_agent",
                      "amount": {"value": 1.25, "currency": "usd"}}]}]}
        result = collect_utc_day(fetch, project_id="proj_agent", now=NOW)
        self.assertEqual(result["utc_day"], "2026-11-04")
        self.assertEqual(result["window_start"], int(NOW.replace(hour=0).timestamp()))
        self.assertEqual(result["window_end"], int(NOW.timestamp()))
        self.assertEqual(result["reported_cost_usd"], "1.25")
        self.assertTrue(urls)

    def test_missing_cost_rows_report_zero_not_proof_of_zero_usage(self):
        result = collect_utc_day(lambda _: {"data": [{"results": []}]},
                                  project_id="proj_agent", now=NOW)
        self.assertEqual(result["reported_cost_usd"], "0")
        self.assertTrue(result["settlement_delay_possible"])

    def test_pending_reservation_blocks_third_run(self):
        records = [dict(run_id=i, state="reserved", utc_day="2026-11-04") for i in (1,2)]
        self.assertFalse(assess(now=NOW, observed_at=NOW, reported_usd="0",
                                reservations=records)["allowed"])

    def test_settled_reservation_not_double_counted(self):
        records = [dict(run_id=1, state="settled", utc_day="2026-11-04")]
        self.assertTrue(assess(now=NOW, observed_at=NOW, reported_usd="2",
                               reservations=records)["allowed"])

    def test_failed_unreconciled_still_reserved(self):
        records = [dict(run_id=1, state="failed_unreconciled", utc_day="2026-11-04")]
        self.assertFalse(assess(now=NOW, observed_at=NOW, reported_usd="6",
                                reservations=records)["allowed"])

    def test_stale_evidence_denied(self):
        self.assertFalse(assess(now=NOW, observed_at=NOW-timedelta(hours=2),
                                reported_usd="0", reservations=[])["allowed"])

    def test_cross_day_fails_closed(self):
        self.assertFalse(assess(now=NOW, observed_at=NOW, reported_usd="0",
                                reservations=[dict(run_id=1,state="reserved",utc_day="2026-11-03")])["allowed"])

    def test_unverified_release_denied(self):
        self.assertFalse(settlement_transition("started","settled",verified=False))
        self.assertTrue(settlement_transition("started","settled",verified=True))

    def test_retry_duplicate_denied(self):
        r=[dict(run_id=1,state="reserved",utc_day="2026-11-04")]*2
        self.assertFalse(assess(now=NOW, observed_at=NOW, reported_usd="0",
                                reservations=r)["allowed"])

if __name__ == "__main__":
    unittest.main()
