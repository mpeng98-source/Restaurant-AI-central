"""PostgreSQL-only tests; the CI job checks TEST_DATABASE_URL before pytest."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

import app.models as models

TEST_MIGRATION_DATABASE_URL = os.getenv("TEST_MIGRATION_DATABASE_URL")
TEST_FIXTURE_DATABASE_URL = os.getenv("TEST_FIXTURE_DATABASE_URL")

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = [pytest.mark.postgres, pytest.mark.skipif(not TEST_DATABASE_URL, reason="real PostgreSQL TEST_DATABASE_URL is required")]


@pytest.fixture
def app_connection():
    engine = create_engine(TEST_DATABASE_URL, pool_size=1, max_overflow=0)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()
    engine.dispose()


def set_scope(connection, organization_id=None, location_ids=(), user_id=None, employee_read=False):
    values = {
        "app.organization_id": str(organization_id) if organization_id else "",
        "app.location_ids": ",".join(str(value) for value in location_ids),
        "app.user_id": str(user_id) if user_id else "",
        "app.can_read_location_employees": "true" if employee_read else "false",
    }
    for key, value in values.items():
        connection.execute(text("SELECT set_config(:key, :value, true)"), {"key": key, "value": value})


def test_restricted_application_role_cannot_bypass_rls(app_connection):
    role = app_connection.execute(text("SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user")).one()
    assert role == (False, False, False, False)
    assert app_connection.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one() is False
    privileges = app_connection.execute(text("SELECT has_table_privilege(current_user, 'role_permissions', 'INSERT') OR has_table_privilege(current_user, 'role_permissions', 'UPDATE') OR has_table_privilege(current_user, 'role_permissions', 'DELETE')")).scalar_one()
    assert privileges is False
    table_security = app_connection.execute(text("""
        SELECT relrowsecurity, relforcerowsecurity
        FROM pg_class WHERE oid = 'locations'::regclass
    """)).one()
    assert table_security == (True, True)


def test_missing_tenant_context_fails_closed(app_connection, test_actors):
    assert app_connection.execute(text("SELECT count(*) FROM locations")).scalar_one() == 0
    set_scope(app_connection, location_ids=[test_actors.location_a])
    assert app_connection.execute(text("SELECT count(*) FROM locations")).scalar_one() == 0
    set_scope(app_connection, test_actors.organization_id)
    assert app_connection.execute(text("SELECT count(*) FROM locations")).scalar_one() == 0


def test_organization_and_location_isolation(app_connection, test_actors):
    set_scope(app_connection, test_actors.organization_id, [test_actors.location_a])
    assert app_connection.execute(text("SELECT count(*) FROM organizations WHERE id = :id"), {"id": test_actors.organization_id}).scalar_one() == 1
    assert app_connection.execute(text("SELECT count(*) FROM organizations WHERE id = :id"), {"id": test_actors.other_organization}).scalar_one() == 0
    visible = set(app_connection.scalars(text("SELECT id FROM locations")))
    assert visible == {test_actors.location_a}
    assert app_connection.execute(text("SELECT count(*) FROM locations WHERE id = :id"), {"id": test_actors.location_b}).scalar_one() == 0

    set_scope(app_connection, test_actors.other_organization, [test_actors.other_location])
    visible_other_tenant = set(app_connection.scalars(text("SELECT id FROM locations")))
    assert visible_other_tenant == {test_actors.other_location}
    assert test_actors.location_a not in visible_other_tenant


def test_employee_rows_are_self_only_until_location_permission_is_set(app_connection, test_actors):
    set_scope(app_connection, test_actors.organization_id, [test_actors.location_a], test_actors.employee_id)
    visible = set(app_connection.scalars(text("SELECT user_id FROM employees WHERE location_id = :location_id"), {"location_id": test_actors.location_a}))
    assert visible == {test_actors.employee_id}
    set_scope(app_connection, test_actors.organization_id, [test_actors.location_a], test_actors.gm_id, employee_read=True)
    assert app_connection.execute(text("SELECT count(*) FROM employees WHERE location_id = :location_id"), {"location_id": test_actors.location_a}).scalar_one() >= 3


def test_application_cannot_change_other_users_role_assignments(app_connection, test_actors):
    set_scope(app_connection, test_actors.organization_id, [test_actors.location_a], test_actors.owner_id)
    role_id = app_connection.execute(text("SELECT role_id FROM user_location_assignments WHERE user_id = :user_id"), {"user_id": test_actors.gm_id}).scalar_one()
    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            app_connection.execute(text("INSERT INTO user_location_assignments (id, user_id, organization_id, location_id, role_id, active) VALUES (:id, :user_id, :org, :location, :role, true)"), {"id": uuid.uuid4(), "user_id": test_actors.gm_id, "org": test_actors.organization_id, "location": test_actors.location_a, "role": role_id})


def test_rls_blocks_cross_location_reads_and_writes(app_connection, test_actors):
    set_scope(app_connection, test_actors.organization_id, [test_actors.location_a], test_actors.owner_id)
    assert app_connection.execute(text("SELECT count(*) FROM locations WHERE id = :id"), {"id": test_actors.location_b}).scalar_one() == 0
    result = app_connection.execute(text("UPDATE locations SET name = 'tampered' WHERE id = :id"), {"id": test_actors.location_b})
    assert result.rowcount == 0
    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            app_connection.execute(text("INSERT INTO locations (id, organization_id, name, code, status) VALUES (:id, :org, 'forbidden', :code, 'active')"), {"id": uuid.uuid4(), "org": test_actors.other_organization, "code": f"denied-{uuid.uuid4().hex[:8]}"})


def test_audit_logs_allow_append_but_reject_update_and_delete(app_connection, test_actors):
    set_scope(app_connection, test_actors.organization_id, [test_actors.location_a], test_actors.owner_id)
    audit_id = uuid.uuid4()
    app_connection.execute(text("""
        INSERT INTO audit_logs (id, organization_id, location_id, user_id, action, metadata)
        VALUES (:id, :org, :location, :user, 'test.append', '{}'::jsonb)
    """), {"id": audit_id, "org": test_actors.organization_id, "location": test_actors.location_a, "user": test_actors.owner_id})
    assert app_connection.execute(text("SELECT has_table_privilege(current_user, 'audit_logs', 'UPDATE') OR has_table_privilege(current_user, 'audit_logs', 'DELETE')")).scalar_one() is False


def test_migration_account_is_separate_and_non_superuser():
    assert TEST_MIGRATION_DATABASE_URL, "TEST_MIGRATION_DATABASE_URL is required"
    engine = create_engine(TEST_MIGRATION_DATABASE_URL)
    with engine.connect() as connection:
        role = connection.execute(text("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
    engine.dispose()
    assert role == ("chubby_migrator", False, False)


def test_audit_trigger_rejects_mutation_even_for_fixture_administrator(test_actors):
    assert TEST_FIXTURE_DATABASE_URL, "TEST_FIXTURE_DATABASE_URL is required for administrator-level trigger verification"
    engine = create_engine(TEST_FIXTURE_DATABASE_URL)
    audit_id = uuid.uuid4()
    with engine.connect() as connection:
        transaction = connection.begin()
        set_scope(connection, test_actors.organization_id, [test_actors.location_a], test_actors.owner_id)
        connection.execute(text("""
            INSERT INTO audit_logs (id, organization_id, location_id, user_id, action, metadata)
            VALUES (:id, :org, :location, :user, 'test.immutable', '{}'::jsonb)
        """), {"id": audit_id, "org": test_actors.organization_id, "location": test_actors.location_a, "user": test_actors.owner_id})
        for statement in (
            "UPDATE audit_logs SET action = 'tampered' WHERE id = :id",
            "DELETE FROM audit_logs WHERE id = :id",
        ):
            with pytest.raises(DBAPIError):
                with connection.begin_nested():
                    connection.execute(text(statement), {"id": audit_id})
        transaction.rollback()
    engine.dispose()


def test_transaction_local_tenant_context_does_not_leak_through_pool():
    engine = create_engine(TEST_DATABASE_URL, pool_size=1, max_overflow=0)
    with engine.connect() as connection:
        connection.execute(text("SELECT set_config('app.organization_id', :value, true)"), {"value": str(uuid.uuid4())})
        connection.commit()
    with engine.connect() as connection:
        leaked = connection.execute(text("SELECT current_setting('app.organization_id', true)")).scalar_one()
        assert leaked in (None, "")
    engine.dispose()
