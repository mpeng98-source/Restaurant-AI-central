import os
import secrets
import uuid
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
TEST_MIGRATION_DATABASE_URL = os.getenv("TEST_MIGRATION_DATABASE_URL") or os.getenv("MIGRATION_DATABASE_URL")
TEST_FIXTURE_DATABASE_URL = os.getenv("TEST_FIXTURE_DATABASE_URL")
if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import app.models as models
from app.main import app
from app.security import hash_password


@dataclass
class TestActors:
    organization_id: uuid.UUID
    location_a: uuid.UUID
    location_b: uuid.UUID
    other_organization: uuid.UUID
    other_location: uuid.UUID
    owner_email: str
    gm_email: str
    employee_email: str
    password: str = field(repr=False)
    owner_id: uuid.UUID
    gm_id: uuid.UUID
    employee_id: uuid.UUID


@pytest.fixture
def api_client():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is required for API integration tests")
    with TestClient(app, base_url="https://testserver") as client:
        yield client


def make_test_actors():
    if not TEST_DATABASE_URL or not TEST_MIGRATION_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL and TEST_MIGRATION_DATABASE_URL are required for PostgreSQL integration tests")
    org_a, loc_a, loc_b, org_b, loc_c = (uuid.uuid4() for _ in range(5))
    owner_id, gm_id, employee_id = (uuid.uuid4() for _ in range(3))
    run_id = uuid.uuid4().hex[:12]
    owner_email = f"owner-{run_id}@tests.example"
    gm_email = f"gm-{run_id}@tests.example"
    employee_email = f"employee-{run_id}@tests.example"
    password = secrets.token_urlsafe(32)
    if not TEST_FIXTURE_DATABASE_URL:
        pytest.skip("TEST_FIXTURE_DATABASE_URL must identify a fixture administrator for test data only")
    admin_engine = create_engine(TEST_FIXTURE_DATABASE_URL)
    with Session(admin_engine) as db, db.begin():
        db.execute(text("SELECT set_config('app.organization_id', :org, true)"), {"org": str(org_a)})
        owner_role = db.scalar(select(models.Role).where(models.Role.name == "Corporate Owner"))
        gm_role = db.scalar(select(models.Role).where(models.Role.name == "General Manager"))
        employee_role = db.scalar(select(models.Role).where(models.Role.name == "Employee"))
        assert owner_role and gm_role and employee_role, "role seed migration has not run"
        db.add(models.Organization(id=org_a, name=f"Test Org {run_id}", slug=f"test-org-{run_id}", status="active"))
        db.flush()
        db.execute(text("SELECT set_config('app.location_ids', :locations, true)"), {"locations": f"{loc_a},{loc_b}"})
        db.add_all([
            models.Location(id=loc_a, organization_id=org_a, name="Test Location A", code=f"T-{run_id}-A"),
            models.Location(id=loc_b, organization_id=org_a, name="Test Location B", code=f"T-{run_id}-B"),
        ])
        db.flush()
        db.execute(text("SELECT set_config('app.organization_id', :org, true)"), {"org": str(org_b)})
        db.execute(text("SELECT set_config('app.location_ids', :locations, true)"), {"locations": str(loc_c)})
        db.add(models.Organization(id=org_b, name=f"Other Test Org {run_id}", slug=f"other-test-org-{run_id}", status="active"))
        db.flush()
        db.add(models.Location(id=loc_c, organization_id=org_b, name="Other Test Location", code=f"T-{run_id}-C"))
        db.flush()
        db.execute(text("SELECT set_config('app.organization_id', :org, true)"), {"org": str(org_a)})
        db.execute(text("SELECT set_config('app.location_ids', :locations, true)"), {"locations": f"{loc_a},{loc_b}"})
        for user_id, email in ((owner_id, owner_email), (gm_id, gm_email), (employee_id, employee_email)):
            db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(user_id)})
            db.add(models.User(id=user_id, email=email, password_hash=hash_password(password)))
            db.flush()
        db.execute(text("SELECT set_config('app.user_id', '', true)"))
        db.execute(text("SELECT set_config('app.can_read_location_employees', 'true', true)"))
        db.add_all([
            models.UserLocationAssignment(user_id=owner_id, organization_id=org_a, location_id=loc_a, role_id=owner_role.id),
            models.UserLocationAssignment(user_id=gm_id, organization_id=org_a, location_id=loc_a, role_id=gm_role.id),
            models.UserLocationAssignment(user_id=employee_id, organization_id=org_a, location_id=loc_a, role_id=employee_role.id),
        ])
        db.add_all([
            models.Employee(user_id=owner_id, organization_id=org_a, location_id=loc_a, first_name="Test", last_name="Owner"),
            models.Employee(user_id=gm_id, organization_id=org_a, location_id=loc_a, first_name="Test", last_name="Manager"),
            models.Employee(user_id=employee_id, organization_id=org_a, location_id=loc_a, first_name="Test", last_name="Employee"),
        ])
    admin_engine.dispose()
    return TestActors(org_a, loc_a, loc_b, org_b, loc_c, owner_email, gm_email, employee_email, password, owner_id, gm_id, employee_id)


@pytest.fixture(scope="session")
def test_actors():
    return make_test_actors()
