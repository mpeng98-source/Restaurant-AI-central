import re
import logging
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from ssl import create_default_context

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as DBSession

from app.authorization import Principal, authenticated_principal, authorize_location, require_csrf, set_db_context, unauthorized
from app.config import settings
from app.db import get_db
from app.models import AuditLog, Employee, Invitation, InvitationLocation, Location, PasswordResetToken, Role, Session as AuthSession, User, UserLocationAssignment
from app.security import hash_password, new_token, password_hasher, token_hash, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
protected_router = APIRouter(prefix="/api/v1", tags=["identity"])
password_pattern = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{12,128}$")
DUMMY_PASSWORD_HASH = password_hasher.hash("not-a-real-password-used-to-equalize-login-work")
RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""
logger = logging.getLogger(__name__)


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class InviteBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: str
    location_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("A valid email is required")
        return normalized


class AcceptInviteBody(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)


class ResetRequestBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class ResetConfirmBody(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=12, max_length=128)


def normalize_email(value: str) -> str:
    normalized = value.strip().casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
        raise HTTPException(status_code=422, detail="A valid email is required")
    return normalized


def check_password_strength(value: str) -> None:
    if not password_pattern.fullmatch(value):
        raise HTTPException(status_code=422, detail="Password must be 12–128 characters and include letters and numbers")


def redis_client(request: Request) -> Redis:
    return request.app.state.redis


def rate_limit_key(request: Request, identity: str, action: str) -> str:
    remote = request.client.host if request.client else "unknown"
    return f"auth-rate:{action}:{token_hash(remote + ':' + identity)}"


def check_rate_limit(redis: Redis, request: Request, identity: str, action: str) -> None:
    key = rate_limit_key(request, identity, action)
    try:
        count = int(redis.eval(RATE_LIMIT_SCRIPT, 1, key, 900))
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable") from exc
    if count > 5:
        raise HTTPException(status_code=429, detail="Too many authentication attempts; try again later")


def send_password_reset_email(email: str, raw_token: str, *, invitation: bool = False) -> None:
    message = EmailMessage()
    message["Subject"] = "Your Chubby AI invitation" if invitation else "Reset your Chubby AI password"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    if invitation:
        message.set_content(
            f"You have been invited to Chubby AI. Accept this single-use invitation within {settings.invite_ttl_hours} hours: "
            f"{settings.frontend_base_url.rstrip('/')}/accept-invitation?token={raw_token}\n"
        )
    else:
        message.set_content(
            "A password reset was requested for your Chubby AI account. "
            f"Use this single-use link within {settings.password_reset_ttl_minutes} minutes: "
            f"{settings.frontend_base_url.rstrip('/')}/reset-password?token={raw_token}\n\n"
            "If you did not request this, you can ignore this message."
        )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as mailer:
            mailer.ehlo()
            mailer.starttls(context=create_default_context())
            mailer.ehlo()
            if settings.smtp_username:
                mailer.login(settings.smtp_username, settings.smtp_password or "")
            mailer.send_message(message)
    except (OSError, smtplib.SMTPException):
        logger.exception("Password reset email delivery failed")


def set_session_cookie(response: Response, value: str, *, httponly: bool) -> None:
    response.set_cookie(
        "chubby_session" if httponly else "chubby_csrf",
        value,
        max_age=settings.session_ttl_hours * 3600,
        httponly=httponly,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def set_user_audit_scope(db: DBSession, user_id: uuid.UUID) -> dict[str, uuid.UUID]:
    assignment = db.scalar(
        select(UserLocationAssignment)
        .where(UserLocationAssignment.user_id == user_id, UserLocationAssignment.active.is_(True))
        .order_by(UserLocationAssignment.organization_id, UserLocationAssignment.location_id)
    )
    if not assignment:
        return {}
    set_db_context(db, user_id=user_id, organization_id=assignment.organization_id, location_ids=[assignment.location_id])
    return {"organization_id": assignment.organization_id, "location_id": assignment.location_id}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db: DBSession = Depends(get_db), redis: Redis = Depends(redis_client)):
    email = normalize_email(body.email)
    check_rate_limit(redis, request, email, "login")
    set_db_context(db, login_email=email)
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    valid = verify_password(body.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if not user or user.status != "active" or not valid:
        db.add(AuditLog(action="auth.login.failed", metadata_json={"email": email[:3] + "…"}))
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    now = datetime.now(timezone.utc)
    session_token, csrf_token = new_token(), new_token()
    set_db_context(db, user_id=user.id)
    audit_scope = set_user_audit_scope(db, user.id)
    if not audit_scope:
        db.rollback()
        raise HTTPException(status_code=401, detail="Invalid email or password")
    session = AuthSession(
        user_id=user.id,
        token_hash=token_hash(session_token),
        csrf_token_hash=token_hash(csrf_token),
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(session)
    db.add(AuditLog(**audit_scope, user_id=user.id, action="auth.login.succeeded", metadata_json={}))
    db.commit()
    redis.delete(rate_limit_key(request, email, "login"))
    set_session_cookie(response, session_token, httponly=True)
    set_session_cookie(response, csrf_token, httponly=False)
    return {"email": user.email, "csrf_token": csrf_token, "expires_at": session.expires_at}


@router.post("/logout", status_code=204)
def logout(response: Response, principal: Principal = Depends(require_csrf), db: DBSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    db.execute(update(AuthSession).where(AuthSession.id == principal.session_id).values(revoked_at=now))
    audit_scope = {}
    if principal.grants:
        grant = principal.grants[0]
        set_db_context(db, user_id=principal.user_id, organization_id=grant.organization_id, location_ids=[grant.location_id])
        audit_scope = {"organization_id": grant.organization_id, "location_id": grant.location_id}
    db.add(AuditLog(**audit_scope, user_id=principal.user_id, action="auth.logout", metadata_json={}))
    db.commit()
    response.delete_cookie("chubby_session", path="/", secure=settings.cookie_secure, httponly=True, samesite="strict")
    response.delete_cookie("chubby_csrf", path="/", secure=settings.cookie_secure, httponly=False, samesite="strict")
    response.status_code = 204
    return response


@router.post("/invitations", status_code=201)
def create_invitation(body: InviteBody, principal: Principal = Depends(require_csrf), db: DBSession = Depends(get_db)):
    if body.role not in {"Corporate Owner", "General Manager", "Employee"}:
        raise HTTPException(status_code=422, detail="Unsupported role")
    email = body.email
    set_db_context(db, user_id=principal.user_id, login_email=email)
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    unique_location_ids = set(body.location_ids)
    if len(unique_location_ids) != len(body.location_ids):
        raise HTTPException(status_code=422, detail="Duplicate location assignments are not allowed")
    grants = [authorize_location(principal, location_id, "user:invite", db) for location_id in unique_location_ids]
    organization_ids = {grant.organization_id for grant in grants}
    if len(organization_ids) != 1:
        raise HTTPException(status_code=422, detail="An invitation must belong to one organization")
    organization_id = next(iter(organization_ids))
    set_db_context(db, user_id=principal.user_id, organization_id=organization_id, location_ids=list(unique_location_ids))
    role_id = db.scalar(select(Role.id).where(Role.name == body.role))
    if not role_id:
        raise HTTPException(status_code=422, detail="Role is not configured")
    invite_token = new_token()
    invitation = Invitation(
        organization_id=organization_id,
        email=email,
        role_id=role_id,
        token_hash=token_hash(invite_token),
        invited_by=principal.user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.invite_ttl_hours),
    )
    db.add(invitation)
    db.flush()
    for location_id in unique_location_ids:
        db.add(InvitationLocation(invitation_id=invitation.id, organization_id=organization_id, location_id=location_id))
    db.add(AuditLog(organization_id=organization_id, user_id=principal.user_id, action="user.invited", entity_type="invitation", entity_id=str(invitation.id), metadata_json={"email": email, "role": body.role}))
    expires_at = invitation.expires_at
    invitation_id = invitation.id
    db.commit()
    if settings.environment in {"development", "test"}:
        return {"invitation_id": invitation_id, "email": email, "role": body.role, "token": invite_token, "expires_at": expires_at}
    if settings.smtp_host and settings.smtp_from_email:
        send_password_reset_email(email, invite_token, invitation=True)
    return {"invitation_id": invitation_id, "email": email, "role": body.role, "expires_at": expires_at}


@router.post("/invitations/accept", status_code=201)
def accept_invitation(body: AcceptInviteBody, db: DBSession = Depends(get_db)):
    check_password_strength(body.password)
    digest = token_hash(body.token)
    set_db_context(db, invite_hash=digest)
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == digest))
    now = datetime.now(timezone.utc)
    if not invitation or invitation.used_at or invitation.expires_at <= now:
        raise HTTPException(status_code=400, detail="Invitation is invalid or expired")
    set_db_context(db, invitation_id=invitation.id)
    location_ids = list(db.scalars(select(InvitationLocation.location_id).where(InvitationLocation.invitation_id == invitation.id)))
    if not location_ids:
        raise HTTPException(status_code=400, detail="Invitation has no location assignments")
    set_db_context(db, login_email=invitation.email)
    if db.scalar(select(User.id).where(func.lower(User.email) == invitation.email)):
        raise HTTPException(status_code=409, detail="An account already exists for this invitation")
    set_db_context(db, organization_id=invitation.organization_id, location_ids=location_ids)
    claim = db.execute(
        update(Invitation)
        .where(Invitation.id == invitation.id, Invitation.used_at.is_(None), Invitation.expires_at > now)
        .values(used_at=now)
    )
    if claim.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=400, detail="Invitation is invalid or expired")
    user_id = uuid.uuid4()
    set_db_context(db, user_id=user_id, organization_id=invitation.organization_id, location_ids=location_ids)
    user = User(id=user_id, email=invitation.email, password_hash=hash_password(body.password), status="active")
    db.add(user)
    db.flush()
    for location_id in location_ids:
        db.add(UserLocationAssignment(user_id=user_id, organization_id=invitation.organization_id, location_id=location_id, role_id=invitation.role_id, active=True))
    db.add(Employee(user_id=user_id, organization_id=invitation.organization_id, location_id=location_ids[0], first_name=body.first_name.strip(), last_name=body.last_name.strip(), status="active"))
    db.add(AuditLog(organization_id=invitation.organization_id, location_id=location_ids[0], user_id=user_id, action="user.invitation.accepted", entity_type="user", entity_id=str(user_id), metadata_json={}))
    db.commit()
    return {"user_id": user_id, "email": user.email, "status": "active"}


@router.post("/password-reset/request", status_code=202)
def request_password_reset(body: ResetRequestBody, request: Request, db: DBSession = Depends(get_db), redis: Redis = Depends(redis_client)):
    email = normalize_email(body.email)
    check_rate_limit(redis, request, email, "password-reset")
    set_db_context(db, login_email=email)
    user = db.scalar(select(User).where(func.lower(User.email) == email, User.status == "active"))
    result: dict[str, str] = {"message": "If the account exists, reset instructions will be provided."}
    if user:
        raw_token = new_token()
        set_db_context(db, user_id=user.id)
        db.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)).values(used_at=datetime.now(timezone.utc)))
        db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash(raw_token), expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_ttl_minutes)))
        audit_scope = set_user_audit_scope(db, user.id)
        db.add(AuditLog(**audit_scope, user_id=user.id, action="auth.password_reset.requested", metadata_json={}))
        if settings.environment in {"development", "test"}:
            result["development_token"] = raw_token
    db.commit()
    if user and settings.environment not in {"development", "test"} and settings.smtp_host and settings.smtp_from_email:
        send_password_reset_email(user.email, raw_token)
    return result


@router.post("/password-reset/confirm")
def confirm_password_reset(body: ResetConfirmBody, db: DBSession = Depends(get_db)):
    check_password_strength(body.password)
    digest = token_hash(body.token)
    set_db_context(db, reset_hash=digest)
    reset = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == digest))
    now = datetime.now(timezone.utc)
    if not reset or reset.used_at or reset.expires_at <= now:
        raise HTTPException(status_code=400, detail="Reset token is invalid or expired")
    set_db_context(db, user_id=reset.user_id)
    user = db.get(User, reset.user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=400, detail="Reset token is invalid or expired")
    claim = db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.id == reset.id, PasswordResetToken.used_at.is_(None), PasswordResetToken.expires_at > now)
        .values(used_at=now)
    )
    if claim.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=400, detail="Reset token is invalid or expired")
    db.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)).values(used_at=now))
    user.password_hash = hash_password(body.password)
    user.session_version += 1
    db.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).values(revoked_at=now))
    audit_scope = set_user_audit_scope(db, user.id)
    db.add(AuditLog(**audit_scope, user_id=user.id, action="auth.password_reset.completed", metadata_json={}))
    db.commit()
    return {"status": "password_updated"}


@protected_router.get("/me")
def current_user(request: Request, response: Response, principal: Principal = Depends(authenticated_principal), db: DBSession = Depends(get_db)):
    csrf_token = request.cookies.get("chubby_csrf")
    if csrf_token:
        response.headers["X-CSRF-Token"] = csrf_token
    set_db_context(db, user_id=principal.user_id)
    employee = db.scalar(select(Employee).where(Employee.user_id == principal.user_id))
    assignments = [
        {"organization_id": str(grant.organization_id), "location_id": str(grant.location_id), "role": grant.role, "permissions": sorted(grant.permissions)}
        for grant in principal.grants
    ]
    return {"user_id": principal.user_id, "email": principal.email, "employee": {"first_name": employee.first_name, "last_name": employee.last_name} if employee else None, "assignments": assignments}


@protected_router.get("/locations")
def list_locations(principal: Principal = Depends(authenticated_principal), db: DBSession = Depends(get_db)):
    locations_by_id: dict[uuid.UUID, Location] = {}
    owner_organizations = {grant.organization_id for grant in principal.grants if grant.role == "Corporate Owner"}
    for organization_id in owner_organizations:
        set_db_context(db, user_id=principal.user_id, organization_id=organization_id, can_read_all_locations=True)
        for location in db.scalars(select(Location).where(Location.organization_id == organization_id)):
            locations_by_id[location.id] = location
    other_ids = {grant.location_id for grant in principal.grants if grant.organization_id not in owner_organizations and "location:read" in grant.permissions}
    for grant in principal.grants:
        if grant.location_id in other_ids and "location:read" in grant.permissions:
            set_db_context(db, user_id=principal.user_id, organization_id=grant.organization_id, location_ids=[grant.location_id])
            location = db.get(Location, grant.location_id)
            if location:
                locations_by_id[location.id] = location
    return [{"id": row.id, "organization_id": row.organization_id, "name": row.name, "code": row.code, "status": row.status} for row in locations_by_id.values()]


@protected_router.get("/locations/{location_id}/dashboard")
def location_dashboard(location_id: uuid.UUID, principal: Principal = Depends(authenticated_principal), db: DBSession = Depends(get_db)):
    grant = authorize_location(principal, location_id, "dashboard:read", db)
    set_db_context(db, user_id=principal.user_id, organization_id=grant.organization_id, location_ids=[location_id])
    from app.models import Location
    location = db.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return {"role": grant.role, "location": {"id": location.id, "name": location.name, "code": location.code}}


@protected_router.get("/locations/{location_id}/employees")
def location_employees(location_id: uuid.UUID, principal: Principal = Depends(authenticated_principal), db: DBSession = Depends(get_db)):
    grant = authorize_location(principal, location_id, "employee:read:location", db)
    set_db_context(db, user_id=principal.user_id, organization_id=grant.organization_id, location_ids=[location_id], can_read_location_employees=True)
    employees = db.scalars(select(Employee).where(Employee.organization_id == grant.organization_id, Employee.location_id == location_id)).all()
    return [{"id": row.id, "first_name": row.first_name, "last_name": row.last_name, "status": row.status} for row in employees]


@protected_router.post("/locations/{location_id}/notifications/read", status_code=204)
def read_notifications(location_id: uuid.UUID, principal: Principal = Depends(require_csrf), db: DBSession = Depends(get_db)):
    grant = authorize_location(principal, location_id, "notification:read:self", db)
    from app.models import Notification
    set_db_context(db, user_id=principal.user_id, organization_id=grant.organization_id, location_ids=[location_id])
    db.execute(update(Notification).where(Notification.location_id == location_id, Notification.user_id == principal.user_id, Notification.read_at.is_(None)).values(read_at=datetime.now(timezone.utc)))
    db.commit()
    return Response(status_code=204)
