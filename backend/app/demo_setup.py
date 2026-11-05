"""Explicit one-time synthetic setup through the restricted application role."""
import json
import re
import sys
import uuid

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select, text

from app.authorization import set_db_context
from app.config import settings
from app.db import SessionLocal
from app.inventory_models import InventoryCategory, InventoryItem, InventoryLocationItem
from app.models import AuditLog, Employee, Location, Organization, Role, User, UserLocationAssignment
from app.security import hash_password

NAMESPACE = uuid.UUID("6d7feb9d-04b0-4dd1-b4c1-6a245f24a280")


def identity(name):
    return uuid.uuid5(NAMESPACE, name)


class TestAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str = Field(min_length=32, max_length=128, repr=False)

    @field_validator("email")
    @classmethod
    def synthetic_email(cls, value):
        if not re.fullmatch(r"[a-z0-9_.-]+@demo\.example", value):
            raise ValueError("Use synthetic @demo.example accounts only")
        return value


class DemoAccounts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner: TestAccount
    gm: TestAccount
    employee: TestAccount


def setup(accounts):
    if settings.environment != "internal-demo":
        raise ValueError("Synthetic setup is restricted to ENVIRONMENT=internal-demo")
    if len({account.email for account in (accounts.owner, accounts.gm, accounts.employee)}) != 3:
        raise ValueError("Use three distinct synthetic users")
    org, loc, second, other_org, other_loc = (identity(name) for name in
        ("organization", "location-a", "location-b", "other-organization", "other-location"))
    with SessionLocal.begin() as db:
        role_name, superuser, bypass = db.execute(text(
            "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
        if role_name != "chubby_app" or superuser or bypass:
            raise ValueError("Setup requires restricted chubby_app, never administrator credentials")
        set_db_context(db, organization_id=org, location_ids=[loc, second])
        if db.get(Organization, org):
            raise ValueError("Demo already exists; setup never overwrites accounts or history")
        db.add(Organization(id=org, name="SYNTHETIC Demo Organization", slug=f"synthetic-internal-demo-{org}"))
        db.flush()
        db.add_all([Location(id=loc, organization_id=org, name="SYNTHETIC Test Location A", code="DEMO-A"),
                    Location(id=second, organization_id=org, name="SYNTHETIC Test Location B", code="DEMO-B")])
        db.flush()
        for key, name in (("owner", "Corporate Owner"), ("gm", "General Manager"), ("employee", "Employee")):
            account = getattr(accounts, key)
            role = db.scalar(select(Role).where(Role.name == name))
            if not role:
                raise ValueError("Required roles missing; apply migrations first")
            set_db_context(db, login_email=account.email)
            if db.scalar(select(User.id).where(User.email == account.email)):
                raise ValueError("Synthetic email already exists; refusing to overwrite")
            user_id = identity(key)
            set_db_context(db, user_id=user_id, organization_id=org, location_ids=[loc])
            db.add(User(id=user_id, email=account.email, password_hash=hash_password(account.password)))
            db.flush()
            db.add(UserLocationAssignment(user_id=user_id, organization_id=org, location_id=loc, role_id=role.id))
            db.add(Employee(user_id=user_id, organization_id=org, location_id=loc,
                            first_name="Synthetic", last_name=key.title()))
            db.add(AuditLog(organization_id=org, location_id=loc, user_id=user_id,
                            action="demo.account.created", entity_type="user", entity_id=str(user_id),
                            metadata_json={"synthetic": True}))
            db.flush()
        set_db_context(db, user_id=identity("owner"), organization_id=org, location_ids=[loc, second])
        category, item = identity("category"), identity("item")
        db.add(InventoryCategory(id=category, organization_id=org, name="SYNTHETIC Ingredients"))
        db.flush()
        db.add(InventoryItem(id=item, organization_id=org, category_id=category, sku="DEMO-FLOUR",
                             name="SYNTHETIC Demo Flour", item_type="ingredient",
                             base_unit_code="g", purchase_unit_code="kg"))
        db.flush()
        db.add_all([InventoryLocationItem(organization_id=org, location_id=where, inventory_item_id=item)
                    for where in (loc, second)])
        db.flush()
        set_db_context(db, organization_id=other_org, location_ids=[other_loc])
        db.add(Organization(id=other_org, name="SYNTHETIC Other Tenant", slug=f"synthetic-isolation-target-{other_org}"))
        db.flush()
        db.add(Location(id=other_loc, organization_id=other_org, name="SYNTHETIC Other Tenant Location", code="DEMO-OTHER"))
        db.flush()
        db.add(AuditLog(organization_id=other_org, location_id=other_loc, action="demo.organization.created",
                        entity_type="organization", entity_id=str(other_org), metadata_json={"synthetic": True}))
    return {"organization_id": str(org), "location_id": str(loc), "second_location_id": str(second),
            "other_location_id": str(other_loc), "item_id": str(item)}


def main():
    # Read credentials from a secret pipe, never command arguments or logged environment.
    try:
        accounts = DemoAccounts.model_validate_json(sys.stdin.read())
    except ValidationError:
        raise SystemExit("Invalid synthetic account input; details suppressed to protect passwords") from None
    print(json.dumps(setup(accounts)))


if __name__ == "__main__":
    main()
