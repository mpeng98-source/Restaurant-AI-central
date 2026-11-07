"""End-to-end API and RLS counting acceptance against restricted real PostgreSQL."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.main import app
from conftest import make_test_actors
from test_inventory_postgres import inventory_fixture, app_connection, set_scope

APP_URL = os.getenv("TEST_DATABASE_URL")
ADMIN_URL = os.getenv("TEST_FIXTURE_DATABASE_URL")
pytestmark = [pytest.mark.postgres, pytest.mark.skipif(not APP_URL or not ADMIN_URL, reason="real PostgreSQL is mandatory for counting integration")]


@pytest.fixture
def test_actors():
    # Authentication acceptance mutates passwords; each count scenario gets a
    # fresh tenant and users, including for the imported inventory fixture.
    return make_test_actors()


def login(client, actors, role):
    email = {"gm": actors.gm_email, "owner": actors.owner_email, "employee": actors.employee_email}[role]
    response = client.post("/api/v1/auth/login", json={"email": email, "password": actors.password})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def path(actors, session_id=None):
    base = f"/api/v1/inventory/locations/{actors.location_a}/count-sessions"
    return f"{base}/{session_id}" if session_id else base


def create(client, actors, headers, **values):
    payload = {"idempotency_key": str(uuid.uuid4()), "assigned_to": str(actors.employee_id), **values}
    response = client.post(path(actors), headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json(), payload


def item(client, actors, fixture):
    response = client.get(f"/api/v1/inventory/locations/{actors.location_a}/catalog")
    assert response.status_code == 200, response.text
    return next(row for row in response.json()["items"] if row["id"] == str(fixture.item_a))


def save(client, actors, session, fixture, sku, headers, quantity="315", unit="g", **extra):
    return client.put(f"{path(actors, session['id'])}/lines/{fixture.item_a}", headers=headers,
                      json={"version": session["version"], "quantity": quantity, "sku": sku, "unit_code": unit, **extra})


def ledger(actors, fixture, movements):
    engine = create_engine(APP_URL)
    with engine.begin() as connection:
        set_scope(connection, actors.organization_id, [actors.location_a], actors.owner_id)
        for movement_type, quantity in movements:
            connection.execute(text("""INSERT INTO stock_movements
                (id, organization_id, location_id, inventory_item_id, movement_type, quantity_delta, unit_code, idempotency_key, actor_id)
                VALUES (:id, :org, :loc, :item, :kind, :quantity, 'g', :key, :actor)"""),
                {"id": uuid.uuid4(), "org": actors.organization_id, "loc": actors.location_a, "item": fixture.item_a,
                 "kind": movement_type, "quantity": Decimal(quantity), "key": str(uuid.uuid4()), "actor": actors.owner_id})
    engine.dispose()


def snapshot(client, actors, session_id):
    response = client.get(f"{path(actors, session_id)}/variance")
    assert response.status_code == 200, response.text
    return response.json()["lines"][0]["snapshot"]


def test_unknown_count_fields_reject_without_mutating_session_or_audit(api_client, test_actors, inventory_fixture):
    a = test_actors
    headers = login(api_client, a, "gm")
    payload = {"idempotency_key": str(uuid.uuid4()), "assigned_to": str(a.employee_id),
               "percentge_threshold": "25"}
    response = api_client.post(path(a), headers=headers, json=payload)
    assert response.status_code == 422, response.text
    assert any(error["type"] == "extra_forbidden" for error in response.json()["detail"])
    assert api_client.get(path(a)).json() == []
    session, _ = create(api_client, a, headers, percentage_threshold="25")
    assert Decimal(session["percentage_threshold"]) == Decimal("25")
    response = api_client.patch(path(a, session["id"]), headers=headers, json={
        "version": session["version"], "assigned_to": str(a.employee_id), "percentge_threshold": "50"})
    assert response.status_code == 422, response.text
    employee = login(api_client, a, "employee")
    response = save(api_client, a, session, inventory_fixture,
                    item(api_client, a, inventory_fixture)["sku"], employee, quanity="999")
    assert response.status_code == 422, response.text
    response = api_client.post(f"{path(a, session['id'])}/submit", headers=employee,
                               json={"version": session["version"], "confirmed": True})
    assert response.status_code == 422, response.text
    current = api_client.get(path(a, session["id"])).json()
    assert current["version"] == session["version"]
    assert current["status"] == "draft"
    assert current["lines"] == []
    assert Decimal(current["percentage_threshold"]) == Decimal("25")
    engine = create_engine(APP_URL)
    with engine.begin() as connection:
        set_scope(connection, a.organization_id, [a.location_a], a.owner_id)
        actions = connection.execute(text("SELECT action FROM audit_logs WHERE entity_id=:id"),
                                     {"id": session["id"]}).scalars().all()
        assert actions == ["inventory.count.created"]
    engine.dispose()


def test_count_acceptance_variance_cutoff_review_and_no_posting(api_client, test_actors, inventory_fixture, app_connection):
    a = test_actors
    ledger(a, inventory_fixture, [("opening", "500"), ("receiving", "200"), ("production_out", "-350"), ("waste", "-10")])
    manager = login(api_client, a, "gm")
    session, _ = create(api_client, a, manager, quantity_threshold="5", percentage_threshold="5")
    employee = login(api_client, a, "employee")
    sku = item(api_client, a, inventory_fixture)["sku"]
    saved = save(api_client, a, session, inventory_fixture, sku, employee, quantity="0.315", unit="kg")
    assert saved.status_code == 200, saved.text
    session = saved.json()
    submitted = api_client.post(f"{path(a, session['id'])}/submit", headers=employee, json={"version": session["version"]})
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["cutoff_at"] == submitted.json()["submitted_at"]
    assert api_client.get(f"{path(a, session['id'])}/variance").status_code == 403
    assert api_client.post(f"{path(a, session['id'])}/submit", headers=employee, json={"version": session["version"]}).status_code == 409
    manager = login(api_client, a, "gm")
    frozen = snapshot(api_client, a, session["id"])
    assert Decimal(frozen["expected_quantity"]) == Decimal("340")
    assert Decimal(frozen["base_quantity"]) == Decimal("315")
    assert Decimal(frozen["variance_quantity"]) == Decimal("-25")
    assert Decimal(frozen["variance_percentage"]) == Decimal("-7.352941")
    assert frozen["status"] == "above_threshold"
    set_scope(app_connection, a.organization_id, [a.location_a], a.owner_id)
    assert app_connection.execute(text("SELECT count(*) FROM stock_movements WHERE inventory_item_id = :id"), {"id": inventory_fixture.item_a}).scalar_one() == 4
    assert app_connection.execute(text("SELECT count(*) FROM audit_logs WHERE entity_id = :id AND action = 'inventory.count.submitted'"), {"id": session["id"]}).scalar_one() == 1
    reviewed = api_client.post(f"{path(a, session['id'])}/review", headers=manager, json={"version": submitted.json()["version"]})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "under_review"
    assert api_client.post(f"{path(a, session['id'])}/approve", headers=manager, json={}).status_code == 404
    ledger(a, inventory_fixture, [("receiving", "100")])
    assert snapshot(api_client, a, session["id"]) == frozen
    assert app_connection.execute(text("SELECT sum(quantity_delta) FROM stock_movements WHERE inventory_item_id = :id"), {"id": inventory_fixture.item_a}).scalar_one() == Decimal("440")
    assert app_connection.execute(text("SELECT count(*) FROM stock_movements WHERE inventory_item_id = :id AND created_at > CAST(:cutoff AS timestamptz)"), {"id": inventory_fixture.item_a, "cutoff": submitted.json()["cutoff_at"]}).scalar_one() == 1
    login(api_client, a, "owner")
    assert snapshot(api_client, a, session["id"]) == frozen


def test_baseline_required_is_not_zero_and_submission_does_not_post(api_client, test_actors, inventory_fixture, app_connection):
    a = test_actors
    headers = login(api_client, a, "employee")
    session, _ = create(api_client, a, headers)
    saved = save(api_client, a, session, inventory_fixture, item(api_client, a, inventory_fixture)["sku"], headers, quantity="0")
    assert saved.status_code == 200, saved.text
    response = api_client.post(f"{path(a, session['id'])}/submit", headers=headers, json={"version": saved.json()["version"]})
    assert response.status_code == 200, response.text
    login(api_client, a, "gm")
    result = snapshot(api_client, a, session["id"])
    assert result["status"] == "baseline_required"
    assert result["expected_quantity"] is None and result["variance_quantity"] is None and result["variance_percentage"] is None
    set_scope(app_connection, a.organization_id, [a.location_a], a.owner_id)
    assert app_connection.execute(text("SELECT count(*) FROM stock_movements WHERE inventory_item_id = :id"), {"id": inventory_fixture.item_a}).scalar_one() == 0


def test_zero_expected_balance_has_undefined_percentage(api_client, test_actors, inventory_fixture):
    a = test_actors
    ledger(a, inventory_fixture, [("opening", "100"), ("waste", "-100")])
    headers = login(api_client, a, "employee")
    session, _ = create(api_client, a, headers)
    saved = save(api_client, a, session, inventory_fixture, item(api_client, a, inventory_fixture)["sku"], headers, quantity="0")
    assert saved.status_code == 200, saved.text
    response = api_client.post(f"{path(a, session['id'])}/submit", headers=headers, json={"version": saved.json()["version"]})
    assert response.status_code == 200, response.text
    login(api_client, a, "gm")
    result = snapshot(api_client, a, session["id"])
    assert Decimal(result["expected_quantity"]) == 0
    assert result["variance_percentage"] is None and result["status"] == "within_threshold"


def test_draft_versions_unique_lines_idempotent_creation_and_removal(api_client, test_actors, inventory_fixture):
    a = test_actors
    headers = login(api_client, a, "employee")
    session, payload = create(api_client, a, headers)
    again = api_client.post(path(a), headers=headers, json=payload)
    assert again.status_code == 201 and again.json()["id"] == session["id"]
    assert api_client.post(f"{path(a, session['id'])}/submit", headers=headers, json={"version": 1}).status_code == 422
    sku = item(api_client, a, inventory_fixture)["sku"]
    saved = save(api_client, a, session, inventory_fixture, sku, headers, quantity="1.25", unit="kg")
    assert saved.status_code == 200, saved.text
    assert save(api_client, a, session, inventory_fixture, sku, headers, quantity="9").status_code == 409
    edited = save(api_client, a, saved.json(), inventory_fixture, sku, headers, quantity="0.315", unit="kg")
    assert edited.status_code == 200, edited.text
    assert len(edited.json()["lines"]) == 1 and Decimal(edited.json()["lines"][0]["quantity"]) == Decimal("0.315")
    removed = api_client.delete(f"{path(a, session['id'])}/lines/{inventory_fixture.item_a}?version={edited.json()['version']}", headers=headers)
    assert removed.status_code == 200 and removed.json()["lines"] == []


def test_decimal_units_sku_validation_and_explicit_item_conversion(api_client, test_actors, inventory_fixture):
    a = test_actors
    headers = login(api_client, a, "employee")
    session, _ = create(api_client, a, headers)
    sku = item(api_client, a, inventory_fixture)["sku"]
    for quantity, unit, submitted_sku in [("-1", "g", sku), (1.2, "g", sku), ("1", "ml", sku), ("1", "g", "wrong-sku")]:
        assert save(api_client, a, session, inventory_fixture, submitted_sku, headers, quantity=quantity, unit=unit).status_code == 422
    engine = create_engine(ADMIN_URL)
    with engine.begin() as c:
        c.execute(text("INSERT INTO inventory_item_unit_conversions (id,organization_id,location_id,inventory_item_id,unit_code,factor_to_stock_unit) VALUES (:id,:org,:loc,:item,'ea',12.5)"),
                  {"id": uuid.uuid4(), "org": a.organization_id, "loc": a.location_a, "item": inventory_fixture.item_a})
    engine.dispose()
    saved = save(api_client, a, session, inventory_fixture, sku, headers, quantity="2", unit="ea")
    assert saved.status_code == 200, saved.text
    submitted = api_client.post(f"{path(a, session['id'])}/submit", headers=headers, json={"version": saved.json()["version"]})
    assert submitted.status_code == 200, submitted.text
    login(api_client, a, "gm")
    assert Decimal(snapshot(api_client, a, session["id"])["base_quantity"]) == Decimal("25")


def test_assignment_changes_revoke_previous_counter_and_cross_scope_access(api_client, test_actors, inventory_fixture):
    a = test_actors
    manager = login(api_client, a, "gm")
    session, _ = create(api_client, a, manager)
    assigned = api_client.patch(path(a, session["id"]), headers=manager, json={"version": session["version"], "assigned_to": str(a.gm_id)})
    assert assigned.status_code == 200, assigned.text
    employee = login(api_client, a, "employee")
    assert api_client.get(path(a, session["id"])).status_code == 404
    assert api_client.get(f"/api/v1/inventory/locations/{a.location_b}/count-sessions").status_code == 403
    assert api_client.get(f"/api/v1/inventory/locations/{a.other_location}/count-sessions").status_code == 403
    assert api_client.post(path(a), headers=employee, json={"idempotency_key": str(uuid.uuid4()), "assigned_to": str(a.gm_id)}).status_code == 403
    login(api_client, a, "owner")
    assert api_client.get(f"/api/v1/inventory/locations/{a.other_location}/count-sessions").status_code == 403


def test_assignment_and_zone_validation(api_client, test_actors, inventory_fixture):
    a = test_actors
    manager = login(api_client, a, "gm")
    for values in ({"assigned_to": str(uuid.uuid4())}, {"storage_zone_id": str(uuid.uuid4())}):
        response = api_client.post(path(a), headers=manager, json={"idempotency_key": str(uuid.uuid4()), "assigned_to": str(a.employee_id), **values})
        assert response.status_code == 422, response.text
    zone = uuid.uuid4()
    engine = create_engine(ADMIN_URL)
    with engine.begin() as c:
        c.execute(text("INSERT INTO inventory_storage_zones (id,organization_id,location_id,code,name) VALUES (:id,:org,:loc,:code,'Freezer')"), {"id": zone, "org": a.organization_id, "loc": a.location_a, "code": str(zone)})
    engine.dispose()
    session, _ = create(api_client, a, manager, storage_zone_id=str(zone))
    employee = login(api_client, a, "employee")
    assert save(api_client, a, session, inventory_fixture, item(api_client, a, inventory_fixture)["sku"], employee).status_code == 422


def test_rls_assignment_missing_context_and_frozen_snapshot(api_client, test_actors, inventory_fixture, app_connection):
    a = test_actors
    headers = login(api_client, a, "employee")
    session, _ = create(api_client, a, headers)
    saved = save(api_client, a, session, inventory_fixture, item(api_client, a, inventory_fixture)["sku"], headers)
    assert saved.status_code == 200, saved.text
    set_scope(app_connection, a.organization_id, [a.location_a], a.employee_id)
    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            app_connection.execute(text("UPDATE inventory_count_sessions SET assigned_to=:user, version=version+1 WHERE id=:id"), {"user": a.gm_id, "id": session["id"]})
    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            app_connection.execute(text("UPDATE inventory_count_lines SET snapshot='{}'::jsonb WHERE session_id=:id"), {"id": session["id"]})
    set_scope(app_connection, a.organization_id, [a.location_a], a.owner_id)
    # Owner can review but cannot silently write lines owned by the employee.
    assert app_connection.execute(text("UPDATE inventory_count_lines SET quantity=999 WHERE session_id=:id"), {"id": session["id"]}).rowcount == 0
    set_scope(app_connection, a.organization_id, [a.location_b], a.employee_id)
    assert app_connection.execute(text("SELECT count(*) FROM inventory_count_sessions WHERE id=:id"), {"id": session["id"]}).scalar_one() == 0
    set_scope(app_connection, a.other_organization, [a.other_location], a.employee_id)
    assert app_connection.execute(text("SELECT count(*) FROM inventory_count_lines WHERE session_id=:id"), {"id": session["id"]}).scalar_one() == 0
    set_scope(app_connection)
    assert app_connection.execute(text("SELECT count(*) FROM inventory_count_sessions")).scalar_one() == 0
    submitted = api_client.post(f"{path(a, session['id'])}/submit", headers=headers, json={"version": saved.json()["version"]})
    assert submitted.status_code == 200, submitted.text
    assert save(api_client, a, submitted.json(), inventory_fixture, item(api_client, a, inventory_fixture)["sku"], headers).status_code == 409
    engine = create_engine(ADMIN_URL)
    with engine.begin() as connection:
        set_scope(connection, a.organization_id, [a.location_a], a.employee_id)
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(text("UPDATE inventory_count_lines SET quantity=999 WHERE session_id=:id"), {"id": session["id"]})
    engine.dispose()


def test_concurrent_draft_edits_and_double_submit_are_serialized(api_client, test_actors, inventory_fixture):
    a = test_actors
    headers = login(api_client, a, "employee")
    session, _ = create(api_client, a, headers)
    sku = item(api_client, a, inventory_fixture)["sku"]
    cookie_values = dict(api_client.cookies)
    barrier = Barrier(2)
    def edit(quantity):
        with TestClient(app, base_url="https://testserver", cookies=cookie_values) as client:
            barrier.wait(timeout=10)
            return save(client, a, session, inventory_fixture, sku, headers, quantity=quantity).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ["315", "316"]))
    assert sorted(results) == [200, 409]
    current = api_client.get(path(a, session["id"])).json()
    assert len(current["lines"]) == 1
    barrier = Barrier(2)
    def submit(_):
        with TestClient(app, base_url="https://testserver", cookies=cookie_values) as client:
            barrier.wait(timeout=10)
            return client.post(f"{path(a, session['id'])}/submit", headers=headers, json={"version": current["version"]}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, [1, 2])) == [200, 409]
    assert api_client.get(path(a, session["id"])).json()["status"] == "submitted"


def test_count_api_requires_session_and_csrf(api_client, test_actors):
    a = test_actors
    assert api_client.get(path(a)).status_code == 401
    login(api_client, a, "employee")
    assert api_client.post(path(a), json={"idempotency_key": str(uuid.uuid4())}).status_code == 403


def test_counting_follows_multiple_location_assignments_and_combined_roles(api_client, test_actors, inventory_fixture, app_connection):
    a = test_actors
    engine = create_engine(ADMIN_URL)
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO user_location_assignments (id,user_id,organization_id,location_id,role_id,active)
          SELECT :id, :user, :org, :loc, id, true FROM roles WHERE name='Employee'"""),
          {"id": uuid.uuid4(), "user": a.employee_id, "org": a.organization_id, "loc": a.location_b})
        connection.execute(text("""INSERT INTO user_location_assignments (id,user_id,organization_id,location_id,role_id,active)
          SELECT :id, :user, :org, :loc, id, true FROM roles WHERE name='General Manager'"""),
          {"id": uuid.uuid4(), "user": a.employee_id, "org": a.organization_id, "loc": a.location_a})
    headers = login(api_client, a, "employee")
    choices = api_client.get("/api/v1/inventory/locations").json()
    assert {row["id"] for row in choices} == {str(a.location_a), str(a.location_b)}
    assert next(row for row in choices if row["id"] == str(a.location_a))["can_review"] is True
    assert api_client.get(f"/api/v1/inventory/locations/{a.location_a}/assignees").status_code == 200
    set_scope(app_connection, a.organization_id, [a.location_a], a.employee_id)
    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            app_connection.execute(text("""INSERT INTO inventory_count_sessions
              (id,organization_id,location_id,created_by,assigned_to,idempotency_key,status,version)
              VALUES (:id,:org,:loc,:user,:user,:key,'draft',1)"""),
              {"id": uuid.uuid4(), "org": a.organization_id, "loc": a.location_b, "user": a.employee_id, "key": str(uuid.uuid4())})
    # The one foundation employee profile is attached to location A; its active
    # location-B assignment still independently authorizes counting at B.
    endpoint = f"/api/v1/inventory/locations/{a.location_b}/count-sessions"
    created = api_client.post(endpoint, headers=headers, json={"idempotency_key": str(uuid.uuid4())})
    assert created.status_code == 201, created.text
    with engine.begin() as connection:
        connection.execute(text("UPDATE user_location_assignments SET active=false WHERE user_id=:user AND location_id=:loc"), {"user": a.employee_id, "loc": a.location_b})
    assert api_client.get(f"{endpoint}/{created.json()['id']}").status_code == 403
    set_scope(app_connection, a.organization_id, [a.location_b], a.employee_id)
    assert app_connection.execute(text("SELECT count(*) FROM inventory_count_sessions WHERE id=:id"), {"id": created.json()["id"]}).scalar_one() == 0
    engine.dispose()


def test_catalog_change_blocks_submission_without_partial_snapshot(api_client, test_actors, inventory_fixture):
    a = test_actors
    headers = login(api_client, a, "employee")
    session, _ = create(api_client, a, headers)
    saved = save(api_client, a, session, inventory_fixture, item(api_client, a, inventory_fixture)["sku"], headers)
    assert saved.status_code == 200, saved.text
    engine = create_engine(ADMIN_URL)
    with engine.begin() as connection:
        connection.execute(text("UPDATE inventory_location_items SET active=false WHERE organization_id=:org AND location_id=:loc AND inventory_item_id=:item"),
                           {"org": a.organization_id, "loc": a.location_a, "item": inventory_fixture.item_a})
    response = api_client.post(f"{path(a, session['id'])}/submit", headers=headers, json={"version": saved.json()["version"]})
    assert response.status_code == 409, response.text
    current = api_client.get(path(a, session["id"])).json()
    assert current["status"] == "draft" and current["version"] == saved.json()["version"] and current["cutoff_at"] is None
    with engine.connect() as connection:
        assert connection.execute(text("SELECT snapshot FROM inventory_count_lines WHERE session_id=:id"), {"id": session["id"]}).scalar_one() is None
    removed = api_client.delete(f"{path(a, session['id'])}/lines/{inventory_fixture.item_a}?version={current['version']}", headers=headers)
    assert removed.status_code == 200 and removed.json()["lines"] == []
    engine.dispose()
