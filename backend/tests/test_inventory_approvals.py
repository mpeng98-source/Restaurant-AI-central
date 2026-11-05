"""Real PostgreSQL acceptance for financial inventory decisions and corrections."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier, Event
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.main import app
from conftest import make_test_actors
from test_inventory_counting import login, create, item, save, ledger, path
from test_inventory_postgres import inventory_fixture, app_connection, set_scope

APP_URL = os.getenv("TEST_DATABASE_URL")
ADMIN_URL = os.getenv("TEST_FIXTURE_DATABASE_URL")
pytestmark = [pytest.mark.postgres, pytest.mark.skipif(not APP_URL or not ADMIN_URL, reason="real PostgreSQL is mandatory for approval acceptance")]


@pytest.fixture
def test_actors():
    return make_test_actors()


def prepare(client, actors, fixture, *, baseline=True, quantity="315", counter="employee"):
    if baseline:
        ledger(actors, fixture, [("opening", "500"), ("receiving", "200"), ("production_out", "-350"), ("waste", "-10")])
    headers = login(client, actors, counter)
    counter_id = actors.employee_id if counter == "employee" else actors.gm_id
    session, _ = create(client, actors, headers, assigned_to=str(counter_id))
    saved = save(client, actors, session, fixture, item(client, actors, fixture)["sku"], headers, quantity=quantity)
    assert saved.status_code == 200, saved.text
    submitted = client.post(f"{path(actors, session['id'])}/submit", headers=headers, json={"version": saved.json()["version"]})
    assert submitted.status_code == 200, submitted.text
    manager = login(client, actors, "gm")
    response = client.post(f"{path(actors, session['id'])}/review", headers=manager, json={"version": submitted.json()["version"]})
    assert response.status_code == 200, response.text
    return response.json(), manager


def decision_payload(report, *, action="approved", reason="Physical count checked against the frozen report", key=None):
    return {"version": report["version"], "snapshot_hash": report["snapshot_hash"], "action": action, "reason": reason,
            "idempotency_key": key or str(uuid.uuid4()), "reviewed_lines": [{"line_id": line["id"], "verdict": "accepted" if action == "approved" else "disputed"} for line in report["lines"]]}


def decide(client, actors, report, headers, payload=None, **values):
    return client.post(f"{path(actors, report['id'])}/decision", headers=headers, json=payload or decision_payload(report, **values))


def query(actors, sql, **values):
    engine = create_engine(APP_URL)
    with engine.begin() as connection:
        set_scope(connection, actors.organization_id, [actors.location_a], actors.gm_id)
        result = connection.execute(text(sql), values).scalar_one()
    engine.dispose()
    return result


def balance(actors, fixture):
    return query(actors, "SELECT coalesce(sum(quantity_delta),0) FROM stock_movements WHERE inventory_item_id=:item", item=fixture.item_a)


@pytest.fixture
def prepared(api_client, test_actors, inventory_fixture):
    report, headers = prepare(api_client, test_actors, inventory_fixture)
    return report, headers


def test_approval_posts_minus25_once_and_final_ledger_is315(api_client, test_actors, inventory_fixture, prepared):
    report, headers = prepared
    payload = decision_payload(report)
    for invalid in ({**payload, "confirmed": True},
                    {**payload, "reviewed_lines": [{**payload["reviewed_lines"][0], "approved": True}]}):
        rejected = decide(api_client, test_actors, report, headers, invalid)
        assert rejected.status_code == 422, rejected.text
        assert any(error["type"] == "extra_forbidden" for error in rejected.json()["detail"])
        assert balance(test_actors, inventory_fixture) == Decimal("340")
        assert query(test_actors, "SELECT count(*) FROM inventory_count_decisions WHERE session_id=:id",
                     id=report["id"]) == 0
    response = decide(api_client, test_actors, report, headers, payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "approved" and result["version"] == report["version"] + 1
    assert len(result["movements"]) == 1
    movement = result["movements"][0]
    assert Decimal(movement["quantity_delta"]) == Decimal("-25")
    assert Decimal(movement["balance_before"]) == Decimal("340") and Decimal(movement["balance_after"]) == Decimal("315")
    assert movement["count_line_id"] == report["lines"][0]["id"]
    assert movement["actor_id"] == str(test_actors.gm_id) and movement["audit_log_id"] == result["decision"]["audit_log_id"]
    assert balance(test_actors, inventory_fixture) == Decimal("315")
    retry = decide(api_client, test_actors, report, headers, payload)
    assert retry.status_code == 200 and retry.json()["decision"]["id"] == result["decision"]["id"]
    assert len(retry.json()["movements"]) == 1
    assert decide(api_client, test_actors, report, headers).status_code == 409
    assert decide(api_client, test_actors, report, headers, {**payload, "reason": "Changed reason"}).status_code == 409
    assert query(test_actors, "SELECT count(*) FROM audit_logs WHERE action='inventory.count.approved'") == 1


def test_rejection_posts_nothing_and_employee_sees_closed_status(api_client, test_actors, inventory_fixture, prepared):
    report, headers = prepared
    payload = decision_payload(report, action="rejected", reason="Disputed quantity; create a fresh count")
    response = decide(api_client, test_actors, report, headers, payload)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected" and response.json()["movements"] == []
    assert balance(test_actors, inventory_fixture) == Decimal("340")
    assert decide(api_client, test_actors, report, headers, payload).status_code == 200
    login(api_client, test_actors, "employee")
    own = api_client.get(path(test_actors, report["id"])).json()
    assert own["status"] == "rejected" and own["decision"]["reason"] == payload["reason"]
    assert own["lines"][0]["snapshot"] is None and "reviewed_lines" not in own["decision"]
    assert query(test_actors, "SELECT count(*) FROM stock_movements WHERE movement_type='count_adjustment'") == 0


def test_baseline_required_cannot_be_approved_but_can_be_rejected(api_client, test_actors, inventory_fixture):
    report, headers = prepare(api_client, test_actors, inventory_fixture, baseline=False)
    assert report["can_approve"] is False
    response = decide(api_client, test_actors, report, headers)
    assert response.status_code == 409 and "baseline" in response.json()["detail"]
    assert query(test_actors, "SELECT count(*) FROM inventory_count_decisions") == 0
    rejected = decide(api_client, test_actors, report, headers, action="rejected")
    assert rejected.status_code == 200, rejected.text
    assert balance(test_actors, inventory_fixture) == 0


def test_zero_variance_closes_report_without_zero_movement(api_client, test_actors, inventory_fixture):
    report, headers = prepare(api_client, test_actors, inventory_fixture, quantity="340")
    response = decide(api_client, test_actors, report, headers)
    assert response.status_code == 200 and response.json()["status"] == "approved", response.text
    assert response.json()["movements"] == []
    assert balance(test_actors, inventory_fixture) == Decimal("340")


@pytest.mark.parametrize("counter,reviewer", [("gm", "gm"), ("employee", "employee")])
def test_counter_cannot_approve_even_if_reviewer_role(api_client, test_actors, inventory_fixture, counter, reviewer):
    report, _headers = prepare(api_client, test_actors, inventory_fixture, counter=counter)
    headers = login(api_client, test_actors, reviewer)
    assert decide(api_client, test_actors, report, headers).status_code == 403
    owner = login(api_client, test_actors, "owner")
    approved = decide(api_client, test_actors, report, owner)
    assert approved.status_code == 200, approved.text
    assert approved.json()["decision"]["decided_by"] == str(test_actors.owner_id)


def test_prior_counter_cannot_decide_after_reassignment(api_client, test_actors, inventory_fixture):
    a = test_actors
    ledger(a, inventory_fixture, [("opening", "500"), ("production_out", "-160")])
    gm = login(api_client, a, "gm")
    session, _ = create(api_client, a, gm, assigned_to=str(a.gm_id))
    saved = save(api_client, a, session, inventory_fixture, item(api_client, a, inventory_fixture)["sku"], gm)
    assert saved.status_code == 200, saved.text
    owner = login(api_client, a, "owner")
    assigned = api_client.patch(path(a, session["id"]), headers=owner, json={"version": saved.json()["version"], "assigned_to": str(a.employee_id)})
    assert assigned.status_code == 200, assigned.text
    employee = login(api_client, a, "employee")
    submitted = api_client.post(f"{path(a, session['id'])}/submit", headers=employee, json={"version": assigned.json()["version"]})
    assert submitted.status_code == 200, submitted.text
    gm = login(api_client, a, "gm")
    reviewed = api_client.post(f"{path(a, session['id'])}/review", headers=gm, json={"version": submitted.json()["version"]})
    assert reviewed.status_code == 200
    assert decide(api_client, a, reviewed.json(), gm).status_code == 403
    owner = login(api_client, a, "owner")
    assert decide(api_client, a, reviewed.json(), owner).status_code == 200


@pytest.mark.parametrize("movements", [[("receiving", "100")], [("receiving", "10"), ("waste", "-10")]])
def test_intervening_ledger_activity_conflicts_even_if_net_zero(api_client, test_actors, inventory_fixture, prepared, movements):
    report, headers = prepared
    ledger(test_actors, inventory_fixture, movements)
    response = decide(api_client, test_actors, report, headers)
    assert response.status_code == 409 and "ledger changed" in response.json()["detail"]
    assert query(test_actors, "SELECT count(*) FROM inventory_count_decisions") == 0
    assert query(test_actors, "SELECT count(*) FROM stock_movements WHERE movement_type='count_adjustment'") == 0


def test_changed_version_hash_or_line_decisions_do_not_post(api_client, test_actors, inventory_fixture, prepared):
    report, headers = prepared
    payload = decision_payload(report)
    for changed in ({"version": report["version"] - 1}, {"snapshot_hash": "0" * 64}, {"reviewed_lines": [{"line_id": str(uuid.uuid4()), "verdict": "accepted"}]}, {"reviewed_lines": [{"line_id": report["lines"][0]["id"], "verdict": "disputed"}]}):
        assert decide(api_client, test_actors, report, headers, {**payload, **changed}).status_code == 409
    assert decide(api_client, test_actors, report, headers, {**payload, "reviewed_lines": payload["reviewed_lines"] * 2}).status_code == 422
    assert decide(api_client, test_actors, report, headers, {**payload, "reason": "  "}).status_code == 422
    assert balance(test_actors, inventory_fixture) == Decimal("340")
    assert query(test_actors, "SELECT count(*) FROM inventory_count_decisions") == 0


def test_revoked_counter_assignment_blocks_approval_not_rejection(api_client, test_actors, inventory_fixture, prepared):
    report, headers = prepared
    engine = create_engine(ADMIN_URL)
    with engine.begin() as c:
        c.execute(text("UPDATE user_location_assignments SET active=false WHERE user_id=:id"), {"id": test_actors.employee_id})
    engine.dispose()
    response = decide(api_client, test_actors, report, headers)
    assert response.status_code == 409 and "assignment changed" in response.json()["detail"]
    assert decide(api_client, test_actors, report, headers, action="rejected").status_code == 200


def test_approval_permission_csrf_and_cross_scope_denial(api_client, test_actors, inventory_fixture, prepared):
    report, headers = prepared
    payload = decision_payload(report)
    assert api_client.post(f"{path(test_actors, report['id'])}/decision", json=payload).status_code == 403
    for location in (test_actors.location_b, test_actors.other_location):
        response = api_client.post(f"/api/v1/inventory/locations/{location}/count-sessions/{report['id']}/decision", headers=headers, json=payload)
        assert response.status_code == 403
    owner = login(api_client, test_actors, "owner")
    assert api_client.post(f"/api/v1/inventory/locations/{test_actors.other_location}/count-sessions/{report['id']}/decision", headers=owner, json=payload).status_code == 403
    employee = login(api_client, test_actors, "employee")
    assert api_client.get(f"/api/v1/inventory/locations/{test_actors.location_a}/approval-dashboard").status_code == 403
    assert decide(api_client, test_actors, report, employee, payload).status_code == 403
    assert query(test_actors, "SELECT count(*) FROM inventory_count_decisions") == 0


@pytest.mark.parametrize("mode", ["retry", "different_keys", "opposite"])
def test_concurrent_decisions_are_exactly_once(api_client, test_actors, inventory_fixture, prepared, mode):
    report, headers = prepared
    cookies = dict(api_client.cookies)
    first = decision_payload(report)
    second = dict(first) if mode == "retry" else decision_payload(report, action="rejected" if mode == "opposite" else "approved")
    barrier = Barrier(2)
    def post(payload):
        with TestClient(app, base_url="https://testserver", cookies=cookies) as client:
            barrier.wait(timeout=10)
            response = decide(client, test_actors, report, headers, payload)
            return response.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(post, [first, second]))
    assert results == ([200, 200] if mode == "retry" else [200, 409])
    assert query(test_actors, "SELECT count(*) FROM inventory_count_decisions") == 1
    state = api_client.get(path(test_actors, report["id"])).json()["status"]
    movements = query(test_actors, "SELECT count(*) FROM stock_movements WHERE movement_type='count_adjustment'")
    assert movements == (1 if state == "approved" else 0)
    assert balance(test_actors, inventory_fixture) == (Decimal("315") if state == "approved" else Decimal("340"))


def test_receipt_racing_approval_is_not_overwritten(api_client, test_actors, inventory_fixture, prepared):
    report, headers = prepared
    cookies = dict(api_client.cookies)
    started = Event()
    engine = create_engine(APP_URL)
    with engine.connect() as c:
        transaction = c.begin()
        set_scope(c, test_actors.organization_id, [test_actors.location_a], test_actors.owner_id)
        c.execute(text("""INSERT INTO stock_movements(id,organization_id,location_id,inventory_item_id,movement_type,quantity_delta,unit_code,idempotency_key,actor_id)
           VALUES(:id,:org,:loc,:item,'receiving',100,'g',:key,:actor)"""), {"id": uuid.uuid4(), "org": test_actors.organization_id, "loc": test_actors.location_a, "item": inventory_fixture.item_a, "key": str(uuid.uuid4()), "actor": test_actors.owner_id})
        def post():
            with TestClient(app, base_url="https://testserver", cookies=cookies) as client:
                started.set()
                return decide(client, test_actors, report, headers).status_code
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(post)
            assert started.wait(5)
            time.sleep(0.2)
            assert not future.done(), "approval must wait for the location ledger lock"
            transaction.commit()
            assert future.result(timeout=10) == 409
    engine.dispose()
    assert balance(test_actors, inventory_fixture) == Decimal("440")


def test_reversal_adds_compensation_once_and_preserves_original(api_client, test_actors, inventory_fixture, prepared):
    report, headers = prepared
    approved = decide(api_client, test_actors, report, headers)
    assert approved.status_code == 200, approved.text
    movement = approved.json()["movements"][0]
    endpoint = f"/api/v1/inventory/locations/{test_actors.location_a}/movements/{movement['id']}"
    preview = api_client.get(f"{endpoint}/reversal-preview")
    assert preview.status_code == 200, preview.text
    payload = {"idempotency_key": str(uuid.uuid4()), "reason": "Correct an approved count after independent review", "expected_balance": preview.json()["expected_balance"]}
    response = api_client.post(f"{endpoint}/reverse", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    assert balance(test_actors, inventory_fixture) == Decimal("340")
    assert len(response.json()["movements"]) == 2
    original = next(row for row in response.json()["movements"] if row["id"] == movement["id"])
    reversal = next(row for row in response.json()["movements"] if row["movement_type"] == "reversal")
    assert Decimal(original["quantity_delta"]) == Decimal("-25") and original["reversed"] is True
    assert Decimal(reversal["quantity_delta"]) == Decimal("25") and Decimal(reversal["balance_before"]) == Decimal("315") and Decimal(reversal["balance_after"]) == Decimal("340")
    assert reversal["reverses_movement_id"] == movement["id"] and reversal["audit_log_id"] != original["audit_log_id"]
    assert api_client.post(f"{endpoint}/reverse", headers=headers, json=payload).status_code == 200
    assert api_client.post(f"{endpoint}/reverse", headers=headers, json={**payload, "idempotency_key": str(uuid.uuid4())}).status_code == 409
    assert query(test_actors, "SELECT count(*) FROM inventory_movement_reversals") == 1
    assert query(test_actors, "SELECT count(*) FROM audit_logs WHERE action='inventory.adjustment.reversed'") == 1


def test_stale_reversal_preview_does_not_erase_receipts(api_client, test_actors, inventory_fixture, prepared):
    report, headers = prepared
    response = decide(api_client, test_actors, report, headers)
    movement = response.json()["movements"][0]
    endpoint = f"/api/v1/inventory/locations/{test_actors.location_a}/movements/{movement['id']}"
    preview = api_client.get(f"{endpoint}/reversal-preview").json()
    ledger(test_actors, inventory_fixture, [("receiving", "100")])
    payload = {"idempotency_key": str(uuid.uuid4()), "reason": "Reconcile count correction", "expected_balance": preview["expected_balance"]}
    assert api_client.post(f"{endpoint}/reverse", headers=headers, json=payload).status_code == 409
    payload["expected_balance"] = api_client.get(f"{endpoint}/reversal-preview").json()["expected_balance"]
    reversed_result = api_client.post(f"{endpoint}/reverse", headers=headers, json=payload)
    assert reversed_result.status_code == 200, reversed_result.text
    assert balance(test_actors, inventory_fixture) == Decimal("440")


def test_reversal_requires_independent_current_location_permission(api_client, test_actors, inventory_fixture):
    report, gm = prepare(api_client, test_actors, inventory_fixture, counter="gm")
    owner = login(api_client, test_actors, "owner")
    approved = decide(api_client, test_actors, report, owner)
    assert approved.status_code == 200, approved.text
    movement = approved.json()["movements"][0]
    endpoint = f"/api/v1/inventory/locations/{test_actors.location_a}/movements/{movement['id']}"
    gm = login(api_client, test_actors, "gm")
    assert api_client.get(f"{endpoint}/reversal-preview").status_code == 403
    assert api_client.post(f"{endpoint}/reverse", headers=gm, json={"idempotency_key": str(uuid.uuid4()), "reason": "Self correction attempt", "expected_balance": "315"}).status_code == 403


def test_decisions_rls_and_immutability_cover_direct_database_writes(api_client, test_actors, inventory_fixture, prepared, app_connection):
    report, headers = prepared
    set_scope(app_connection, test_actors.organization_id, [test_actors.location_a], test_actors.gm_id)
    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            app_connection.execute(text("UPDATE inventory_count_sessions SET status='approved',version=version+1 WHERE id=:id"), {"id": report["id"]})
    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            app_connection.execute(text("""INSERT INTO stock_movements(id,organization_id,location_id,inventory_item_id,movement_type,quantity_delta,unit_code,idempotency_key,actor_id)
              VALUES(:id,:org,:loc,:item,'count_adjustment',-25,'g',:key,:actor)"""),
              {"id": uuid.uuid4(), "org": test_actors.organization_id, "loc": test_actors.location_a, "item": inventory_fixture.item_a, "key": str(uuid.uuid4()), "actor": test_actors.gm_id})
    approved = decide(api_client, test_actors, report, headers)
    assert approved.status_code == 200, approved.text
    d = approved.json()["decision"]
    m = approved.json()["movements"][0]
    for table in ("inventory_count_decisions", "inventory_adjustment_approvals", "inventory_movement_reversals"):
        assert app_connection.execute(text(f"SELECT has_table_privilege(current_user,'{table}','UPDATE') OR has_table_privilege(current_user,'{table}','DELETE') OR has_table_privilege(current_user,'{table}','TRUNCATE')")).scalar_one() is False
    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            app_connection.execute(text("""INSERT INTO inventory_adjustment_approvals(id,organization_id,location_id,count_line_id,status,decided_by,decided_at,reason,decision_id)
              VALUES(:id,:org,:loc,:line,'approved',:actor,now(),'forged',:decision)"""), {"id": uuid.uuid4(), "org": test_actors.organization_id, "loc": test_actors.location_a, "line": report["lines"][0]["id"], "actor": test_actors.gm_id, "decision": d["id"]})
    for org, loc in ((None, None), (None, test_actors.location_a), (test_actors.organization_id, None), (test_actors.other_organization, test_actors.other_location), (test_actors.organization_id, test_actors.location_b)):
        set_scope(app_connection, org, [loc] if loc else [], test_actors.gm_id)
        assert app_connection.execute(text("SELECT count(*) FROM inventory_count_decisions WHERE id=:id"), {"id": d["id"]}).scalar_one() == 0
    engine = create_engine(ADMIN_URL)
    with engine.begin() as connection:
        for statement, identifier in (("UPDATE inventory_count_decisions SET reason='tamper' WHERE id=:id", d["id"]), ("DELETE FROM stock_movements WHERE id=:id", m["id"]), ("UPDATE audit_logs SET action='tamper' WHERE id=:id", d["audit_log_id"])):
            with pytest.raises(DBAPIError):
                with connection.begin_nested():
                    connection.execute(text(statement), {"id": identifier})
    engine.dispose()


def two_line_report(client, actors, fixture, second_baseline):
    from types import SimpleNamespace
    second = uuid.uuid4()
    engine = create_engine(ADMIN_URL)
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO inventory_items(id,organization_id,sku,name,item_type,base_unit_code,purchase_unit_code)
          VALUES(:id,:org,:sku,'Second ingredient','ingredient','g','kg')"""), {"id": second, "org": actors.organization_id, "sku": f"SECOND-{second}"})
        connection.execute(text("INSERT INTO inventory_location_items(id,organization_id,location_id,inventory_item_id) VALUES(:id,:org,:loc,:item)"),
                           {"id": uuid.uuid4(), "org": actors.organization_id, "loc": actors.location_a, "item": second})
    engine.dispose()
    other = SimpleNamespace(item_a=second)
    for entry in [fixture] + ([other] if second_baseline else []):
        ledger(actors, entry, [("opening", "500"), ("production_out", "-160")])
    headers = login(client, actors, "employee")
    session, _ = create(client, actors, headers)
    for entry in (fixture, other):
        response = save(client, actors, session, entry, item(client, actors, entry)["sku"], headers)
        assert response.status_code == 200, response.text
        session = response.json()
    submitted = client.post(f"{path(actors, session['id'])}/submit", headers=headers, json={"version": session["version"]})
    assert submitted.status_code == 200, submitted.text
    manager = login(client, actors, "gm")
    report = client.post(f"{path(actors, session['id'])}/review", headers=manager, json={"version": submitted.json()["version"]})
    assert report.status_code == 200, report.text
    return report.json(), manager


def test_all_lines_must_be_reviewed_and_partial_approval_never_posts(api_client, test_actors, inventory_fixture):
    report, headers = two_line_report(api_client, test_actors, inventory_fixture, second_baseline=False)
    payload = decision_payload(report)
    assert decide(api_client, test_actors, report, headers, {**payload, "reviewed_lines": payload["reviewed_lines"][:1]}).status_code == 409
    mixed = [dict(line) for line in payload["reviewed_lines"]]
    mixed[1]["verdict"] = "disputed"
    assert decide(api_client, test_actors, report, headers, {**payload, "reviewed_lines": mixed}).status_code == 409
    assert decide(api_client, test_actors, report, headers, payload).status_code == 409
    assert query(test_actors, "SELECT count(*) FROM stock_movements WHERE movement_type='count_adjustment'") == 0
    rejected = decide(api_client, test_actors, report, headers, {**payload, "action": "rejected", "reviewed_lines": mixed})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["movements"] == [] and len(rejected.json()["decision"]["reviewed_lines"]) == 2


def test_late_posting_failure_rolls_back_the_entire_decision(api_client, test_actors, inventory_fixture):
    report, headers = two_line_report(api_client, test_actors, inventory_fixture, second_baseline=True)
    # Force the second line in the posting order to fail the inherited unit guard.
    changed = max(report["lines"], key=lambda line: uuid.UUID(line["id"]).int)
    engine = create_engine(ADMIN_URL)
    with engine.begin() as connection:
        connection.execute(text("UPDATE inventory_items SET base_unit_code='kg' WHERE id=:id"), {"id": changed["inventory_item_id"]})
    engine.dispose()
    response = decide(api_client, test_actors, report, headers)
    assert response.status_code == 409, response.text
    for table in ("inventory_count_decisions", "inventory_adjustment_approvals"):
        assert query(test_actors, f"SELECT count(*) FROM {table}") == 0
    assert query(test_actors, "SELECT count(*) FROM stock_movements WHERE movement_type='count_adjustment'") == 0
    assert query(test_actors, "SELECT count(*) FROM audit_logs WHERE action='inventory.count.approved'") == 0
    assert api_client.get(path(test_actors, report["id"])).json()["status"] == "under_review"


@pytest.mark.parametrize('same_key', [True, False])
def test_concurrent_reversals_post_one_compensating_movement(api_client, test_actors, inventory_fixture, prepared, same_key):
    report, headers = prepared
    approved = decide(api_client, test_actors, report, headers)
    assert approved.status_code == 200, approved.text
    movement = approved.json()['movements'][0]
    endpoint = f"/api/v1/inventory/locations/{test_actors.location_a}/movements/{movement['id']}/reverse"
    first = {'idempotency_key': str(uuid.uuid4()), 'reason': 'Concurrent correction independently reviewed', 'expected_balance': '315'}
    second = {**first, 'idempotency_key': first['idempotency_key'] if same_key else str(uuid.uuid4())}
    cookies = dict(api_client.cookies)
    barrier = Barrier(2)
    def post(payload):
        with TestClient(app, base_url='https://testserver', cookies=cookies) as client:
            barrier.wait(timeout=10)
            return client.post(endpoint, headers=headers, json=payload).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(post, [first, second])) == ([200, 200] if same_key else [200, 409])
    assert query(test_actors, "SELECT count(*) FROM stock_movements WHERE movement_type='reversal'") == 1
    assert balance(test_actors, inventory_fixture) == Decimal('340')


def test_revoked_approver_cannot_use_an_old_session_or_database_context(api_client, test_actors, inventory_fixture, prepared, app_connection):
    report, headers = prepared
    engine = create_engine(ADMIN_URL)
    with engine.begin() as connection:
        connection.execute(text('UPDATE user_location_assignments SET active=false WHERE user_id=:id'), {'id':test_actors.gm_id})
    engine.dispose()
    assert decide(api_client, test_actors, report, headers).status_code == 403
    set_scope(app_connection, test_actors.organization_id, [test_actors.location_a], test_actors.gm_id)
    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            app_connection.execute(text("SELECT inventory_decide_count(:org,:loc,:report,:v,:digest,'approved','revoked reviewer',:key,'[]'::jsonb)"),
                                   {'org':test_actors.organization_id,'loc':test_actors.location_a,'report':report['id'],'v':report['version'],'digest':report['snapshot_hash'],'key':str(uuid.uuid4())})


def test_overwriting_a_draft_line_does_not_erase_four_eyes_history(api_client, test_actors, inventory_fixture):
    a = test_actors
    ledger(a, inventory_fixture, [('opening', '500'), ('production_out', '-160')])
    manager = login(api_client, a, 'gm')
    session, _ = create(api_client, a, manager, assigned_to=str(a.gm_id))
    saved = save(api_client, a, session, inventory_fixture, item(api_client, a, inventory_fixture)['sku'], manager, quantity='316')
    assert saved.status_code == 200, saved.text
    owner = login(api_client, a, 'owner')
    reassigned = api_client.patch(path(a, session['id']), headers=owner, json={'version':saved.json()['version'], 'assigned_to':str(a.employee_id)})
    assert reassigned.status_code == 200, reassigned.text
    employee = login(api_client, a, 'employee')
    overwritten = save(api_client, a, reassigned.json(), inventory_fixture, item(api_client, a, inventory_fixture)['sku'], employee, quantity='315')
    assert overwritten.status_code == 200, overwritten.text
    assert overwritten.json()['lines'][0]['counted_by'] == str(a.employee_id)
    submitted = api_client.post(f"{path(a, session['id'])}/submit", headers=employee, json={'version':overwritten.json()['version']})
    assert submitted.status_code == 200, submitted.text
    manager = login(api_client, a, 'gm')
    reviewed = api_client.post(f"{path(a, session['id'])}/review", headers=manager, json={'version':submitted.json()['version']})
    assert reviewed.status_code == 200, reviewed.text
    report = reviewed.json()
    assert {row['id'] for row in report['counters']} == {str(a.employee_id), str(a.gm_id)}
    assert report['four_eyes_blocked'] is True
    assert decide(api_client, a, report, manager).status_code == 403
    owner = login(api_client, a, 'owner')
    approved = decide(api_client, a, report, owner)
    assert approved.status_code == 200, approved.text
    manager = login(api_client, a, 'gm')
    movement = approved.json()['movements'][0]
    assert api_client.get(f"/api/v1/inventory/locations/{a.location_a}/movements/{movement['id']}/reversal-preview").status_code == 403
