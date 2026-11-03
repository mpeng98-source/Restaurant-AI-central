import uuid

import pytest
from fastapi import HTTPException

from app.authorization import LocationGrant, Principal, authorize_inventory_location


def principal_with(role: str, permissions: set[str]) -> tuple[Principal, uuid.UUID, uuid.UUID]:
    organization_id, location_id = uuid.uuid4(), uuid.uuid4()
    principal = Principal(
        user_id=uuid.uuid4(),
        email="inventory-test@example.invalid",
        session_id=uuid.uuid4(),
        csrf_hash="test-hash",
        grants=[LocationGrant(organization_id, location_id, role, permissions)],
    )
    return principal, organization_id, location_id


def test_employee_can_count_only_at_an_assigned_location():
    employee, _organization_id, assigned_location = principal_with(
        "Employee", {"inventory:read", "inventory:count"}
    )
    assert authorize_inventory_location(employee, assigned_location, "inventory:count", db=None).role == "Employee"
    with pytest.raises(HTTPException) as denied_permission:
        authorize_inventory_location(employee, assigned_location, "inventory:approve", db=None)
    assert denied_permission.value.status_code == 403

    with pytest.raises(HTTPException) as denied_location:
        authorize_inventory_location(employee, uuid.uuid4(), "inventory:count", db=None)
    assert denied_location.value.status_code == 403


def test_general_manager_can_approve_only_at_an_assigned_location():
    manager, _organization_id, assigned_location = principal_with(
        "General Manager", {"inventory:read", "inventory:count", "inventory:approve"}
    )
    assert authorize_inventory_location(manager, assigned_location, "inventory:approve", db=None).role == "General Manager"
    with pytest.raises(HTTPException) as denied_location:
        authorize_inventory_location(manager, uuid.uuid4(), "inventory:approve", db=None)
    assert denied_location.value.status_code == 403
