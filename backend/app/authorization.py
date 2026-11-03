import hmac
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.db import get_db
from app.models import Location, Permission, Role, RolePermission, Session as AuthSession, User, UserLocationAssignment
from app.security import token_hash


INVENTORY_PERMISSION_KEYS = frozenset(
    {"inventory:read", "inventory:count", "inventory:approve", "inventory:catalog:manage"}
)


@dataclass
class LocationGrant:
    organization_id: UUID
    location_id: UUID
    role: str
    permissions: set[str] = field(default_factory=set)


@dataclass
class Principal:
    user_id: UUID
    email: str
    session_id: UUID
    csrf_hash: str
    grants: list[LocationGrant]

    def grants_for(self, location_id: UUID) -> list[LocationGrant]:
        return [grant for grant in self.grants if grant.location_id == location_id]

    def has_permission(self, key: str, location_id: UUID | None = None) -> bool:
        grants = self.grants if location_id is None else self.grants_for(location_id)
        return any(key in grant.permissions for grant in grants)


def unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Cookie"})


def set_db_context(db: DBSession, *, user_id: UUID | None = None, organization_id: UUID | None = None,
                   location_ids: list[UUID] | None = None, login_email: str | None = None,
                   session_hash: str | None = None, invite_hash: str | None = None,
                   invitation_id: UUID | None = None, reset_hash: str | None = None,
                   can_read_location_employees: bool = False,
                   can_read_all_locations: bool = False) -> None:
    values = {
        "app.user_id": str(user_id) if user_id else "",
        "app.organization_id": str(organization_id) if organization_id else "",
        "app.location_ids": ",".join(str(value) for value in (location_ids or [])),
        "app.login_email": (login_email or "").lower(),
        "app.session_token_hash": session_hash or "",
        "app.invitation_token_hash": invite_hash or "",
        "app.invitation_id": str(invitation_id) if invitation_id else "",
        "app.password_reset_token_hash": reset_hash or "",
        "app.can_read_location_employees": "true" if can_read_location_employees else "false",
        "app.can_read_all_locations": "true" if can_read_all_locations else "false",
    }
    for key, value in values.items():
        db.execute(select(func.set_config(key, value, True)))


from fastapi import Request


def authenticated_principal(request: Request, db: DBSession = Depends(get_db)) -> Principal:
    raw_token = request.cookies.get("chubby_session")
    if not raw_token:
        raise unauthorized()
    digest = token_hash(raw_token)
    set_db_context(db, session_hash=digest)
    auth_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest))
    if not auth_session or auth_session.revoked_at is not None or auth_session.expires_at <= datetime.now(timezone.utc):
        raise unauthorized()
    set_db_context(db, user_id=auth_session.user_id)
    user = db.get(User, auth_session.user_id)
    if not user or user.status != "active":
        raise unauthorized()
    rows = db.execute(
        select(UserLocationAssignment.organization_id, UserLocationAssignment.location_id, Role.name, Permission.key)
        .join(Role, Role.id == UserLocationAssignment.role_id)
        .outerjoin(RolePermission, RolePermission.role_id == Role.id)
        .outerjoin(Permission, Permission.id == RolePermission.permission_id)
        .where(UserLocationAssignment.user_id == user.id, UserLocationAssignment.active.is_(True))
    ).all()
    grants_by_key: dict[tuple[UUID, UUID, str], LocationGrant] = {}
    for organization_id, location_id, role, permission in rows:
        key = (organization_id, location_id, role)
        grant = grants_by_key.setdefault(key, LocationGrant(organization_id, location_id, role))
        if permission:
            grant.permissions.add(permission)
    return Principal(user.id, user.email, auth_session.id, auth_session.csrf_token_hash, list(grants_by_key.values()))


def require_csrf(request: Request, principal: Principal = Depends(authenticated_principal), db: DBSession = Depends(get_db)) -> Principal:
    cookie = request.cookies.get("chubby_csrf") or ""
    header = request.headers.get("x-csrf-token") or ""
    if not cookie or not header or not hmac.compare_digest(cookie, header) or not hmac.compare_digest(token_hash(header), principal.csrf_hash):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    return principal


def authorize_location(principal: Principal, location_id: UUID, permission: str, db: DBSession) -> LocationGrant:
    grants = principal.grants_for(location_id)
    for owner_grant in (grant for grant in principal.grants if grant.role == "Corporate Owner"):
        if any(permission in candidate.permissions for candidate in grants):
            break
        set_db_context(db, user_id=principal.user_id, organization_id=owner_grant.organization_id, location_ids=[location_id])
        location = db.get(Location, location_id)
        if location and location.organization_id == owner_grant.organization_id and permission in owner_grant.permissions:
            return LocationGrant(owner_grant.organization_id, location_id, owner_grant.role, set(owner_grant.permissions))
    if not grants:
        raise HTTPException(status_code=403, detail="Location access denied")
    permitted = [grant for grant in grants if permission in grant.permissions]
    if not permitted:
        raise HTTPException(status_code=403, detail="Permission denied")
    return permitted[0]


def authorize_inventory_location(
    principal: Principal, location_id: UUID, permission: str, db: DBSession
) -> LocationGrant:
    """Require an inventory permission and the principal's assigned location grant.

    Inventory routes should call this helper for every location-specific request;
    PostgreSQL RLS remains an independent tenant/location boundary.
    """

    if permission not in INVENTORY_PERMISSION_KEYS:
        raise HTTPException(status_code=400, detail="Unknown inventory permission")
    return authorize_location(principal, location_id, permission, db)
