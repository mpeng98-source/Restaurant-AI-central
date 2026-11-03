"""Location-scoped counting APIs. Submission freezes proposals and never posts stock."""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.authorization import LocationGrant, Principal, authenticated_principal, authorize_inventory_location, require_csrf, set_db_context
from app.db import get_db
from app.inventory_models import InventoryCountLine, InventoryCountSession, InventoryItem, InventoryItemUnitConversion, InventoryLocationItem, InventoryStorageZone, InventoryUnit
from app.inventory_units import convert_item_quantity, convert_quantity
from app.models import AuditLog, Employee, Location, Permission, RolePermission, UserLocationAssignment

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory counts"])


class DecimalBody(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def reject_binary_float(cls, value):
        if isinstance(value, float):
            raise ValueError("Send Decimal quantities as strings")
        return value


class CreateSession(DecimalBody):
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r"\S")
    assigned_to: uuid.UUID | None = None
    storage_zone_id: uuid.UUID | None = None
    quantity_threshold: Decimal = Field(default=Decimal("0"), ge=0, max_digits=24, decimal_places=6, allow_inf_nan=False)
    percentage_threshold: Decimal = Field(default=Decimal("5"), ge=0, max_digits=18, decimal_places=6, allow_inf_nan=False)


class VersionBody(BaseModel):
    version: int = Field(ge=1)


class AssignmentBody(VersionBody, DecimalBody):
    assigned_to: uuid.UUID
    storage_zone_id: uuid.UUID | None = None
    quantity_threshold: Decimal = Field(default=Decimal("0"), ge=0, max_digits=24, decimal_places=6, allow_inf_nan=False)
    percentage_threshold: Decimal = Field(default=Decimal("5"), ge=0, max_digits=18, decimal_places=6, allow_inf_nan=False)


class CountLineBody(VersionBody, DecimalBody):
    sku: str = Field(min_length=1, max_length=80)
    quantity: Decimal = Field(ge=0, max_digits=24, decimal_places=6, allow_inf_nan=False)
    unit_code: str = Field(min_length=1, max_length=24)
    note: str | None = Field(default=None, max_length=2000)
    photo_object_key: str | None = Field(default=None, max_length=512)


def scope(db, principal, location_id, permission="inventory:read"):
    grant = authorize_inventory_location(principal, location_id, permission, db)
    # A person may hold several roles. Combine only grants at this location or
    # owner grants in this verified organization, preserving all valid rights.
    permissions = set().union(*(candidate.permissions for candidate in principal.grants
                               if candidate.organization_id == grant.organization_id
                               and (candidate.location_id == location_id or candidate.role == "Corporate Owner")))
    grant = LocationGrant(grant.organization_id, grant.location_id, grant.role, permissions)
    reviewer = bool({"inventory:approve", "inventory:catalog:manage"} & grant.permissions)
    set_db_context(db, user_id=principal.user_id, organization_id=grant.organization_id,
                   location_ids=[location_id], can_read_location_employees=reviewer)
    return grant, reviewer


def require_reviewer(reviewer):
    if not reviewer:
        raise HTTPException(403, "Manager or owner inventory review permission required")


def assignees(db, organization_id, location_id):
    return db.execute(
        select(UserLocationAssignment.user_id, Employee.first_name, Employee.last_name)
        .outerjoin(Employee, Employee.user_id == UserLocationAssignment.user_id)
        .join(RolePermission, RolePermission.role_id == UserLocationAssignment.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(UserLocationAssignment.organization_id == organization_id, UserLocationAssignment.location_id == location_id,
               UserLocationAssignment.active.is_(True), Permission.key == "inventory:count")
        .distinct().order_by(Employee.first_name, Employee.last_name)
    ).all()


def validate_assignment(db, organization_id, location_id, user_id, zone_id):
    if user_id not in {row.user_id for row in assignees(db, organization_id, location_id)}:
        raise HTTPException(422, "Counter must be an active employee assigned to this location")
    if zone_id and not db.scalar(select(InventoryStorageZone.id).where(
        InventoryStorageZone.id == zone_id, InventoryStorageZone.organization_id == organization_id,
        InventoryStorageZone.location_id == location_id, InventoryStorageZone.active.is_(True))):
        raise HTTPException(422, "Storage zone is not active at this location")


def load_session(db, location_id, session_id, lock=False):
    query = select(InventoryCountSession).where(InventoryCountSession.id == session_id, InventoryCountSession.location_id == location_id)
    if lock:
        query = query.with_for_update()
    session = db.scalar(query)
    if not session:
        raise HTTPException(404, "Count session not found")
    return session


def check_version(session, version, status="draft"):
    if session.version != version or session.status != status:
        raise HTTPException(409, "Session changed or is no longer editable. Reload the latest version.")


def require_counter(session, principal):
    if session.assigned_to != principal.user_id:
        raise HTTPException(403, "Only the assigned counter can edit or submit this session")


def session_json(db, session, reviewer=False, with_lines=True):
    result = {
        "id": str(session.id), "organization_id": str(session.organization_id), "location_id": str(session.location_id),
        "assigned_to": str(session.assigned_to), "storage_zone_id": str(session.storage_zone_id) if session.storage_zone_id else None,
        "version": session.version, "status": session.status, "created_at": session.created_at,
        "submitted_at": session.submitted_at, "cutoff_at": session.cutoff_at,
        "quantity_threshold": str(session.quantity_threshold), "percentage_threshold": str(session.percentage_threshold),
    }
    if with_lines:
        rows = db.execute(select(InventoryCountLine, InventoryItem).join(InventoryItem, InventoryItem.id == InventoryCountLine.inventory_item_id)
                          .where(InventoryCountLine.session_id == session.id).order_by(InventoryItem.sku)).all()
        result["lines"] = [{
            "id": str(line.id), "inventory_item_id": str(line.inventory_item_id),
            "sku": line.snapshot["sku"] if line.snapshot else item.sku,
            "name": line.snapshot["name"] if line.snapshot else item.name,
            "quantity": str(line.quantity), "unit_code": line.unit_code, "note": line.note,
            "photo_object_key": line.photo_object_key, "counted_by": str(line.counted_by),
            "snapshot": line.snapshot if reviewer else None,
        } for line, item in rows]
    return result


def audit(db, session, principal, action):
    db.add(AuditLog(organization_id=session.organization_id, location_id=session.location_id,
                    user_id=principal.user_id, action=action, entity_type="inventory_count_session",
                    entity_id=str(session.id), metadata_json={"version": session.version, "status": session.status}))


def finish(db, session, principal, reviewer, action):
    try:
        db.flush()
        db.refresh(session)
        result = session_json(db, session, reviewer)
        audit(db, session, principal, action)
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Count conflicts with an existing record; reload before retrying") from exc
    except DBAPIError as exc:
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "P0001":
            raise HTTPException(409, "The count no longer matches its assignment or catalog configuration. Reload before retrying.") from exc
        raise


@router.get("/locations")
def inventory_locations(principal: Principal = Depends(authenticated_principal), db: Session = Depends(get_db)):
    result = {}
    for grant in principal.grants:
        if "inventory:read" not in grant.permissions:
            continue
        owner = grant.role == "Corporate Owner"
        set_db_context(db, user_id=principal.user_id, organization_id=grant.organization_id,
                       location_ids=[grant.location_id], can_read_all_locations=owner)
        for location in db.scalars(select(Location).where(Location.status == "active")):
            entry = result.setdefault(str(location.id), {"id": str(location.id), "name": location.name, "code": location.code,
                                                         "can_review": False, "can_count": False})
            entry["can_review"] |= bool({"inventory:approve", "inventory:catalog:manage"} & grant.permissions)
            entry["can_count"] |= "inventory:count" in grant.permissions
    return sorted(result.values(), key=lambda row: row["name"])


@router.get("/locations/{location_id}/catalog")
def catalog(location_id: uuid.UUID, principal: Principal = Depends(authenticated_principal), db: Session = Depends(get_db)):
    _grant, _reviewer = scope(db, principal, location_id)
    units = {unit.code: unit for unit in db.scalars(select(InventoryUnit))}
    items = []
    for item, enabled in db.execute(select(InventoryItem, InventoryLocationItem).join(InventoryLocationItem, InventoryLocationItem.inventory_item_id == InventoryItem.id)
                                    .where(InventoryLocationItem.location_id == location_id, InventoryItem.active.is_(True), InventoryLocationItem.active.is_(True))):
        explicit = set(db.scalars(select(InventoryItemUnitConversion.unit_code).where(InventoryItemUnitConversion.location_id == location_id, InventoryItemUnitConversion.inventory_item_id == item.id)))
        items.append({"id": str(item.id), "sku": item.sku, "name": item.name, "base_unit_code": item.base_unit_code,
                      "storage_zone_id": str(enabled.storage_zone_id) if enabled.storage_zone_id else None,
                      "units": [{"code": unit.code, "name": unit.name} for unit in units.values()
                                if unit.dimension == units[item.base_unit_code].dimension or unit.code in explicit]})
    zones = [{"id": str(zone.id), "name": zone.name} for zone in db.scalars(select(InventoryStorageZone).where(InventoryStorageZone.location_id == location_id, InventoryStorageZone.active.is_(True)))]
    return {"items": sorted(items, key=lambda item: item["sku"]), "zones": zones}


@router.get("/locations/{location_id}/assignees")
def list_assignees(location_id: uuid.UUID, principal: Principal = Depends(authenticated_principal), db: Session = Depends(get_db)):
    grant, reviewer = scope(db, principal, location_id)
    require_reviewer(reviewer)
    return [{"id": str(row.user_id), "name": f"{row.first_name} {row.last_name}" if row.first_name else f"Assigned counter {str(row.user_id)[:8]}"}
            for row in assignees(db, grant.organization_id, location_id)]


@router.get("/locations/{location_id}/count-sessions")
def list_sessions(location_id: uuid.UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                  principal: Principal = Depends(authenticated_principal), db: Session = Depends(get_db)):
    _grant, reviewer = scope(db, principal, location_id)
    sessions = db.scalars(select(InventoryCountSession).where(InventoryCountSession.location_id == location_id)
                          .order_by(InventoryCountSession.created_at.desc(), InventoryCountSession.id).limit(limit).offset(offset))
    return [session_json(db, session, reviewer, with_lines=False) for session in sessions]


@router.post("/locations/{location_id}/count-sessions", status_code=201)
def create_session(location_id: uuid.UUID, body: CreateSession, principal: Principal = Depends(require_csrf), db: Session = Depends(get_db)):
    grant, reviewer = scope(db, principal, location_id)
    assigned_to = body.assigned_to or principal.user_id
    if not reviewer and (assigned_to != principal.user_id or body.quantity_threshold != 0 or body.percentage_threshold != 5):
        raise HTTPException(403, "Only managers can assign counters or configure variance thresholds")
    if not reviewer and "inventory:count" not in grant.permissions:
        raise HTTPException(403, "Counting permission required")
    validate_assignment(db, grant.organization_id, location_id, assigned_to, body.storage_zone_id)
    existing = db.scalar(select(InventoryCountSession).where(InventoryCountSession.location_id == location_id, InventoryCountSession.idempotency_key == body.idempotency_key))
    if existing:
        if existing.created_by != principal.user_id or (existing.assigned_to, existing.storage_zone_id, existing.quantity_threshold, existing.percentage_threshold) != (assigned_to, body.storage_zone_id, body.quantity_threshold, body.percentage_threshold):
            raise HTTPException(409, "Idempotency key was used with a different count request")
        return session_json(db, existing, reviewer)
    session = InventoryCountSession(organization_id=grant.organization_id, location_id=location_id, created_by=principal.user_id,
                                    assigned_to=assigned_to, storage_zone_id=body.storage_zone_id, idempotency_key=body.idempotency_key,
                                    version=1, quantity_threshold=body.quantity_threshold, percentage_threshold=body.percentage_threshold)
    db.add(session)
    return finish(db, session, principal, reviewer, "inventory.count.created")


@router.get("/locations/{location_id}/count-sessions/{session_id}")
def get_session(location_id: uuid.UUID, session_id: uuid.UUID, principal: Principal = Depends(authenticated_principal), db: Session = Depends(get_db)):
    _grant, reviewer = scope(db, principal, location_id)
    return session_json(db, load_session(db, location_id, session_id), reviewer)


@router.patch("/locations/{location_id}/count-sessions/{session_id}")
def assign_session(location_id: uuid.UUID, session_id: uuid.UUID, body: AssignmentBody,
                   principal: Principal = Depends(require_csrf), db: Session = Depends(get_db)):
    grant, reviewer = scope(db, principal, location_id)
    require_reviewer(reviewer)
    session = load_session(db, location_id, session_id, lock=True)
    check_version(session, body.version)
    validate_assignment(db, grant.organization_id, location_id, body.assigned_to, body.storage_zone_id)
    if body.storage_zone_id and db.scalar(select(InventoryCountLine.id).join(InventoryLocationItem, (InventoryLocationItem.inventory_item_id == InventoryCountLine.inventory_item_id) & (InventoryLocationItem.location_id == location_id))
                                         .where(InventoryCountLine.session_id == session_id, InventoryLocationItem.storage_zone_id.is_distinct_from(body.storage_zone_id)).limit(1)):
        raise HTTPException(422, "Saved count lines are outside the selected zone")
    session.assigned_to, session.storage_zone_id = body.assigned_to, body.storage_zone_id
    session.quantity_threshold, session.percentage_threshold = body.quantity_threshold, body.percentage_threshold
    session.version += 1
    return finish(db, session, principal, reviewer, "inventory.count.assigned")


@router.put("/locations/{location_id}/count-sessions/{session_id}/lines/{item_id}")
def save_line(location_id: uuid.UUID, session_id: uuid.UUID, item_id: uuid.UUID, body: CountLineBody,
              principal: Principal = Depends(require_csrf), db: Session = Depends(get_db)):
    grant, reviewer = scope(db, principal, location_id, "inventory:count")
    session = load_session(db, location_id, session_id, lock=True)
    require_counter(session, principal)
    check_version(session, body.version)
    row = db.execute(select(InventoryItem, InventoryLocationItem).join(InventoryLocationItem, InventoryLocationItem.inventory_item_id == InventoryItem.id)
                     .where(InventoryItem.id == item_id, InventoryItem.active.is_(True), InventoryLocationItem.location_id == location_id, InventoryLocationItem.active.is_(True))).first()
    if not row or (session.storage_zone_id and row[1].storage_zone_id != session.storage_zone_id):
        raise HTTPException(422, "Item is not enabled in this session location and zone")
    item = row[0]
    if body.sku != item.sku:
        raise HTTPException(422, "SKU does not match the inventory item")
    unit = db.get(InventoryUnit, body.unit_code)
    stock_unit = db.get(InventoryUnit, item.base_unit_code)
    factor = db.scalar(select(InventoryItemUnitConversion.factor_to_stock_unit).where(InventoryItemUnitConversion.inventory_item_id == item_id, InventoryItemUnitConversion.location_id == location_id, InventoryItemUnitConversion.unit_code == body.unit_code))
    try:
        if not unit or not stock_unit:
            raise ValueError("Unknown inventory unit")
        normalized = convert_item_quantity(body.quantity, factor) if factor is not None else convert_quantity(body.quantity, unit, stock_unit)
        if normalized >= Decimal("1000000000000000000"):
            raise ValueError("Converted quantity exceeds supported precision")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.photo_object_key and not body.photo_object_key.startswith(f"{grant.organization_id}/{location_id}/"):
        raise HTTPException(422, "Photo metadata must belong to this organization and location")
    line = db.scalar(select(InventoryCountLine).where(InventoryCountLine.session_id == session_id, InventoryCountLine.inventory_item_id == item_id))
    if not line:
        line = InventoryCountLine(organization_id=grant.organization_id, location_id=location_id, session_id=session_id, inventory_item_id=item_id)
        db.add(line)
    line.quantity, line.unit_code, line.note = body.quantity, body.unit_code, body.note
    line.photo_object_key, line.counted_by = body.photo_object_key, principal.user_id
    session.version += 1
    return finish(db, session, principal, reviewer, "inventory.count.line_saved")


@router.delete("/locations/{location_id}/count-sessions/{session_id}/lines/{item_id}")
def remove_line(location_id: uuid.UUID, session_id: uuid.UUID, item_id: uuid.UUID, version: int = Query(ge=1),
                principal: Principal = Depends(require_csrf), db: Session = Depends(get_db)):
    _grant, reviewer = scope(db, principal, location_id, "inventory:count")
    session = load_session(db, location_id, session_id, lock=True)
    require_counter(session, principal)
    check_version(session, version)
    line = db.scalar(select(InventoryCountLine).where(InventoryCountLine.session_id == session_id, InventoryCountLine.inventory_item_id == item_id))
    if not line:
        raise HTTPException(404, "Count line not found")
    db.delete(line)
    session.version += 1
    return finish(db, session, principal, reviewer, "inventory.count.line_removed")


@router.post("/locations/{location_id}/count-sessions/{session_id}/submit")
def submit_session(location_id: uuid.UUID, session_id: uuid.UUID, body: VersionBody,
                   principal: Principal = Depends(require_csrf), db: Session = Depends(get_db)):
    _grant, reviewer = scope(db, principal, location_id, "inventory:count")
    session = load_session(db, location_id, session_id, lock=True)
    require_counter(session, principal)
    check_version(session, body.version)
    if not db.scalar(select(InventoryCountLine.id).where(InventoryCountLine.session_id == session_id).limit(1)):
        raise HTTPException(422, "Add at least one confirmed count before submission")
    session.status = "submitted"
    session.version += 1
    return finish(db, session, principal, reviewer, "inventory.count.submitted")


@router.get("/locations/{location_id}/count-sessions/{session_id}/variance")
def variance_report(location_id: uuid.UUID, session_id: uuid.UUID, principal: Principal = Depends(authenticated_principal), db: Session = Depends(get_db)):
    _grant, reviewer = scope(db, principal, location_id)
    require_reviewer(reviewer)
    session = load_session(db, location_id, session_id)
    if session.status == "draft":
        raise HTTPException(409, "Submit the count before reviewing frozen variance")
    return session_json(db, session, reviewer=True)


@router.post("/locations/{location_id}/count-sessions/{session_id}/review")
def begin_review(location_id: uuid.UUID, session_id: uuid.UUID, body: VersionBody,
                 principal: Principal = Depends(require_csrf), db: Session = Depends(get_db)):
    _grant, reviewer = scope(db, principal, location_id)
    require_reviewer(reviewer)
    session = load_session(db, location_id, session_id, lock=True)
    check_version(session, body.version, "submitted")
    session.status = "under_review"
    session.version += 1
    return finish(db, session, principal, reviewer, "inventory.count.review_started")
