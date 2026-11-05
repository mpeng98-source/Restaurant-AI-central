"""Read-only SQL settlement assessment on a transactionally locked day row.

This intentionally DOES NOT update reservation states or release funds.
The authenticated proof and finalization procedure must be designed separately.
"""
from decimal import Decimal
from dev_agent_settlement_policy import assess


def assess_locked_day(conn, *, project_id, day, now):
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""
                SELECT reported_usd, cost_observed_at
                FROM dev_agent_control.daily_budget
                WHERE project_id=%s AND utc_day=%s FOR UPDATE
            """, (project_id, day))
            row = cur.fetchone()
            if row is None:
                return {"allowed": False, "reason": "missing daily budget"}
            reported, observed = row
            if observed is None:
                return {"allowed": False, "reason": "missing cost evidence"}
            cur.execute("""
                SELECT run_id, state, utc_day
                FROM dev_agent_control.run_reservation
                WHERE project_id=%s AND utc_day=%s
                ORDER BY run_id FOR UPDATE
            """, (project_id, day))
            reservations = [
                {"run_id": run_id, "state": state, "utc_day": utc_day.isoformat()}
                for run_id, state, utc_day in cur.fetchall()
            ]
            return assess(now=now, observed_at=observed,
                          reported_usd=reported, reservations=reservations)
