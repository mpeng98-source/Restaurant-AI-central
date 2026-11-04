import unittest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock
from dev_agent_locked_settlement import assess_locked_day

NOW = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)

def db(row, records):
    cursor = MagicMock()
    cursor.fetchone.return_value = row
    cursor.fetchall.return_value = records
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn, cursor

class LockedSettlementTests(unittest.TestCase):
    def test_no_budget_denied(self):
        conn, cur = db(None, [])
        self.assertFalse(assess_locked_day(conn,project_id="proj_agent",day=NOW.date(),now=NOW)["allowed"])

    def test_pending_reservations_limit_exposure(self):
        records=[(1,"reserved",date(2026,11,4)),(2,"started",date(2026,11,4))]
        conn,cur=db(("0",NOW),records)
        self.assertFalse(assess_locked_day(conn,project_id="proj_agent",day=NOW.date(),now=NOW)["allowed"])
        self.assertTrue(all("FOR UPDATE" in q.args[0] for q in cur.execute.call_args_list))

    def test_settled_record_not_counted_twice(self):
        conn,_=db(("2",NOW),[(1,"settled",date(2026,11,4))])
        self.assertTrue(assess_locked_day(conn,project_id="proj_agent",day=NOW.date(),now=NOW)["allowed"])

    def test_missing_cost_observation_denied(self):
        conn,_=db(("0",None),[])
        self.assertFalse(assess_locked_day(conn,project_id="proj_agent",day=NOW.date(),now=NOW)["allowed"])

if __name__ == "__main__":
    unittest.main()
