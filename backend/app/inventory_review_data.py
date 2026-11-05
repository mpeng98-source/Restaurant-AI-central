"""Read models for immutable report decisions and their ledger trace."""
from sqlalchemy import select, text

from app.inventory_models import InventoryCountDecision, InventoryCountLine, StockMovement
from app.models import Employee


def review_data(db, session, reviewer, with_lines):
    decision = db.scalar(select(InventoryCountDecision).where(InventoryCountDecision.session_id == session.id))
    result = {"decision": None}
    if decision:
        result["decision"] = {"id": str(decision.id), "action": decision.action, "reason": decision.reason,
                              "decided_by": str(decision.decided_by), "decided_at": decision.decided_at,
                              "audit_log_id": str(decision.audit_log_id)}
        if reviewer:
            result["decision"]["reviewed_lines"] = decision.reviewed_lines
    if not reviewer or not with_lines or session.status == "draft":
        return result
    lines = list(db.scalars(select(InventoryCountLine).where(InventoryCountLine.session_id == session.id)))
    counters = set(db.scalars(text("SELECT * FROM inventory_report_counter_ids(:report)"), {"report": session.id}))
    names = {employee.user_id: f"{employee.first_name} {employee.last_name}" for employee in db.scalars(select(Employee).where(Employee.user_id.in_(counters)))}
    result["counters"] = [{"id": str(counter), "name": names.get(counter)} for counter in sorted(counters, key=str)]
    actor = db.scalar(text("SELECT current_setting('app.user_id', true)"))
    allowed = db.scalar(text("SELECT inventory_can(:org,:loc,'inventory:approve')"), {"org": session.organization_id, "loc": session.location_id})
    independent = bool(allowed) and actor not in {str(counter) for counter in counters}
    baseline_required = [str(line.id) for line in lines if not line.snapshot or line.snapshot.get("expected_quantity") is None]
    changed = list(db.scalars(select(StockMovement.inventory_item_id).where(
        StockMovement.organization_id == session.organization_id, StockMovement.location_id == session.location_id,
        StockMovement.inventory_item_id.in_([line.inventory_item_id for line in lines]), StockMovement.created_at > session.cutoff_at).distinct()))
    assignments_changed = db.scalar(text("""SELECT EXISTS (
        SELECT 1 FROM inventory_report_counter_ids(:report) AS c(counter)
        WHERE NOT EXISTS (SELECT 1 FROM user_location_assignments a JOIN role_permissions rp ON rp.role_id=a.role_id
          JOIN permissions p ON p.id=rp.permission_id WHERE a.user_id=c.counter AND a.organization_id=:org
          AND a.location_id=:loc AND a.active AND p.key='inventory:count'))"""),
        {"report": session.id, "org": session.organization_id, "loc": session.location_id})
    result.update({
        "snapshot_hash": db.scalar(text("SELECT inventory_report_digest(:id)"), {"id": session.id}),
        "can_approve": independent and session.status == "under_review" and not baseline_required and not changed and not assignments_changed,
        "can_reject": independent and session.status == "under_review",
        "four_eyes_blocked": actor in {str(counter) for counter in counters},
        "approval_blockers": {"baseline_required_lines": baseline_required, "ledger_changed_items": [str(item) for item in changed], "counter_assignment_changed": bool(assignments_changed)},
        "movements": [],
    })
    if decision:
        movements = list(db.scalars(select(StockMovement).where(StockMovement.decision_id == decision.id).order_by(StockMovement.created_at, StockMovement.id)))
        reversed_ids = {movement.reverses_movement_id for movement in movements if movement.reverses_movement_id}
        result["movements"] = [{
            "id": str(movement.id), "inventory_item_id": str(movement.inventory_item_id), "count_line_id": str(movement.count_line_id),
            "movement_type": movement.movement_type, "quantity_delta": str(movement.quantity_delta), "unit_code": movement.unit_code,
            "balance_before": str(movement.balance_before), "balance_after": str(movement.balance_after),
            "reason": movement.reason, "actor_id": str(movement.actor_id), "created_at": movement.created_at,
            "count_cutoff_at": movement.count_cutoff_at, "audit_log_id": str(movement.audit_log_id),
            "reverses_movement_id": str(movement.reverses_movement_id) if movement.reverses_movement_id else None,
            "can_reverse": independent and movement.movement_type == "count_adjustment" and movement.id not in reversed_ids,
            "reversed": movement.id in reversed_ids,
        } for movement in movements]
    return result
