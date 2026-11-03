"""One-time owner bootstrap; invoke explicitly after migrations using app credentials."""
import os
import re
import uuid

from sqlalchemy import select

from app.authorization import set_db_context
from app.db import SessionLocal
from app.models import AuditLog, Employee, Location, Role, User, UserLocationAssignment
from app.security import hash_password


def main() -> None:
    email = os.environ.get("BOOTSTRAP_OWNER_EMAIL", "").strip().casefold()
    password = os.environ.get("BOOTSTRAP_OWNER_PASSWORD", "")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise SystemExit("BOOTSTRAP_OWNER_EMAIL must be a valid email")
    if len(password) < 12 or len(password) > 128 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise SystemExit("BOOTSTRAP_OWNER_PASSWORD must be 12–128 chars and include letters and numbers")

    organization_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    location_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    with SessionLocal.begin() as db:
        set_db_context(db, login_email=email)
        if db.scalar(select(User.id).where(User.email == email)):
            raise SystemExit("An account with that email already exists; bootstrap is one-time")
        set_db_context(db, organization_id=organization_id, location_ids=[location_id])
        location = db.get(Location, location_id)
        role = db.scalar(select(Role).where(Role.name == "Corporate Owner"))
        if not location or not role:
            raise SystemExit("Seed organization, Burbank location, or Corporate Owner role is missing")
        user_id = uuid.uuid4()
        set_db_context(db, user_id=user_id, organization_id=organization_id, location_ids=[location_id])
        user = User(id=user_id, email=email, password_hash=hash_password(password), status="active")
        db.add(user)
        db.flush()
        db.add(UserLocationAssignment(user_id=user_id, organization_id=organization_id, location_id=location_id, role_id=role.id, active=True))
        db.add(Employee(user_id=user_id, organization_id=organization_id, location_id=location_id, first_name="Chubby", last_name="Owner", status="active"))
        db.add(AuditLog(organization_id=organization_id, location_id=location_id, user_id=user_id, action="user.bootstrap.created", entity_type="user", entity_id=str(user_id), metadata_json={}))
    print(f"Bootstrapped Corporate Owner {email}; remove bootstrap credentials from the environment.")


if __name__ == "__main__":
    main()
