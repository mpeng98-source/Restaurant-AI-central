"""Human approval endpoints; all posting and idempotency rules also run in PostgreSQL."""
import json
import uuid
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.authorization import Principal, authenticated_principal, require_csrf
from app.db import get_db
from app.inventory_counts import DecimalBody, load_session, scope, session_json
from app.inventory_models import InventoryCountSession, StockMovement

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory approvals"])


class ReviewedLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_id: uuid.UUID
    verdict: Literal["accepted", "disputed"]


class DecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["approved", "rejected"]
    reason: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r"\S")
    reviewed_lines: list[ReviewedLine] = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        if not value.strip():
            raise ValueError("A decision reason is required")
        return value.strip()

    @field_validator("reviewed_lines")
    @classmethod
    def unique_lines(cls, value):
        if len({line.line_id for line in value}) != len(value):
            raise ValueError("Each count line must be reviewed exactly once")
        return value


class ReversalBody(DecimalBody):
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r"\S")
    reason: str = Field(min_length=1, max_length=2000)
    expected_balance: Decimal = Field(max_digits=24, decimal_places=6, allow_inf_nan=False)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        if not value.strip():
            raise ValueError("A correction reason is required")
        return value.strip()


def database_conflict(db, exc):
    db.rollback()
    code = getattr(exc.orig, "sqlstate", None)
    if code == "22003":
        raise HTTPException(422, "Converted inventory quantity exceeds supported Decimal precision") from exc
    if code == "42501":
        raise HTTPException(403, "Location approval permission and an independent reviewer are required") from exc
    if code == "P0002":
        raise HTTPException(404, "Inventory report or adjustment not found") from exc
    if code in {"P0001", "23505", "23514", "23503"}:
        # Domain errors contain fixed validation messages only, never SQL/DSNs.
        detail = str(exc.orig).split("\n", 1)[0] if code == "P0001" else "Decision conflicts with existing inventory records"
        raise HTTPException(409, detail) from exc
    raise exc


@router.get("/locations/{location_id}/approval-dashboard")
def approval_dashboard(location_id: uuid.UUID, state: Literal["pending", "reviewed", "all"] = "pending",
                       limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                       principal: Principal = Depends(authenticated_principal), db: Session = Depends(get_db)):
    scope(db, principal, location_id, "inventory:approve")
    statuses = {"pending": ["submitted", "under_review"], "reviewed": ["approved", "rejected"], "all": ["submitted", "under_review", "approved", "rejected"]}[state]
    reports = list(db.scalars(select(InventoryCountSession).where(InventoryCountSession.location_id == location_id, InventoryCountSession.status.in_(statuses))
                             .order_by(InventoryCountSession.submitted_at.desc(), InventoryCountSession.id).limit(limit).offset(offset)))
    return [session_json(db, report, reviewer=True, with_lines=False) for report in reports]


@router.post("/locations/{location_id}/count-sessions/{session_id}/decision")
def decide_report(location_id: uuid.UUID, session_id: uuid.UUID, body: DecisionBody,
                  principal: Principal = Depends(require_csrf), db: Session = Depends(get_db)):
    grant, _reviewer = scope(db, principal, location_id, "inventory:approve")
    try:
        db.execute(text("""SELECT inventory_decide_count(:org,:loc,:report,:version,:digest,:action,:reason,:key,CAST(:choices AS jsonb))"""),
                   {"org": grant.organization_id, "loc": location_id, "report": session_id, "version": body.version,
                    "digest": body.snapshot_hash, "action": body.action, "reason": body.reason, "key": body.idempotency_key,
                    "choices": json.dumps([{"line_id": str(line.line_id), "verdict": line.verdict} for line in body.reviewed_lines])})
        db.expire_all()
        result = session_json(db, load_session(db, location_id, session_id), reviewer=True)
        db.commit()
        return result
    except DBAPIError as exc:
        database_conflict(db, exc)


@router.get("/locations/{location_id}/movements/{movement_id}/reversal-preview")
def reversal_preview(location_id: uuid.UUID, movement_id: uuid.UUID,
                     principal: Principal = Depends(authenticated_principal), db: Session = Depends(get_db)):
    scope(db, principal, location_id, "inventory:approve")
    movement = db.scalar(select(StockMovement).where(StockMovement.id == movement_id, StockMovement.location_id == location_id, StockMovement.movement_type == "count_adjustment"))
    if not movement:
        raise HTTPException(404, "Count adjustment not found")
    session_id = db.scalar(text("SELECT session_id FROM inventory_count_decisions WHERE id=:id"), {"id": movement.decision_id})
    report = session_json(db, load_session(db, location_id, session_id), reviewer=True)
    if not next((row["can_reverse"] for row in report["movements"] if row["id"] == str(movement_id)), False):
        raise HTTPException(403 if report["four_eyes_blocked"] else 409, "Adjustment cannot be reversed by this reviewer or was already reversed")
    balance = db.scalar(text("SELECT coalesce(sum(quantity_delta),0) FROM stock_movements WHERE organization_id=:org AND location_id=:loc AND inventory_item_id=:item"),
                        {"org": movement.organization_id, "loc": location_id, "item": movement.inventory_item_id})
    return {"movement_id": str(movement_id), "session_id": str(session_id), "expected_balance": str(balance),
            "quantity_delta": str(-movement.quantity_delta), "balance_after": str(balance - movement.quantity_delta), "unit_code": movement.unit_code}


@router.post("/locations/{location_id}/movements/{movement_id}/reverse")
def reverse_adjustment(location_id: uuid.UUID, movement_id: uuid.UUID, body: ReversalBody,
                       principal: Principal = Depends(require_csrf), db: Session = Depends(get_db)):
    grant, _reviewer = scope(db, principal, location_id, "inventory:approve")
    try:
        reversal_id = db.scalar(text("SELECT inventory_reverse_count_movement(:org,:loc,:original,:key,:reason,:balance)"),
                                {"org": grant.organization_id, "loc": location_id, "original": movement_id,
                                 "key": body.idempotency_key, "reason": body.reason, "balance": body.expected_balance})
        session_id = db.scalar(text("SELECT d.session_id FROM stock_movements m JOIN inventory_count_decisions d ON d.id=m.decision_id WHERE m.id=:id"), {"id": movement_id})
        if not session_id:
            raise HTTPException(404, "Count report not found")
        db.expire_all()
        result = session_json(db, load_session(db, location_id, session_id), reviewer=True)
        result["reversal_id"] = str(reversal_id)
        db.commit()
        return result
    except DBAPIError as exc:
        database_conflict(db, exc)
