"""Inventory tenant isolation and ledger tests; all run against real PostgreSQL."""

import os
import uuid
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

import app.inventory_models as inventory_models


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
TEST_FIXTURE_DATABASE_URL = os.getenv("TEST_FIXTURE_DATABASE_URL")
TEST_MIGRATION_DATABASE_URL = os.getenv("TEST_MIGRATION_DATABASE_URL")


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not (TEST_DATABASE_URL and TEST_MIGRATION_DATABASE_URL and TEST_FIXTURE_DATABASE_URL),
        reason="real PostgreSQL app, migration-owner, and fixture-admin URLs are required",
    ),
]


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


@dataclass(frozen=True)
class InventoryFixture:
    item_a: uuid.UUID
    item_b: uuid.UUID
    category_a: uuid.UUID
    category_b: uuid.UUID
    location_item_a: uuid.UUID
    location_item_b: uuid.UUID
    item_a_other_location: uuid.UUID


def make_inventory_fixture(test_actors):
    run_id = uuid.uuid4().hex[:10]
    category_a, category_b = uuid.uuid4(), uuid.uuid4()
    item_a, item_b = uuid.uuid4(), uuid.uuid4()
    location_item_a, location_item_b, item_a_other_location = (uuid.uuid4() for _ in range(3))
    engine = create_engine(TEST_FIXTURE_DATABASE_URL)
    with Session(engine) as db, db.begin():
        db.execute(text("SELECT set_config('app.organization_id', :org, true)"), {"org": str(test_actors.organization_id)})
        db.execute(text("SELECT set_config('app.location_ids', :locations, true)"), {"locations": str(test_actors.location_a)})
        db.add(inventory_models.InventoryCategory(id=category_a, organization_id=test_actors.organization_id, name=f"Food-{run_id}"))
        db.add(inventory_models.InventoryItem(
            id=item_a,
            organization_id=test_actors.organization_id,
            category_id=category_a,
            sku=f"FOOD-{run_id}",
            name=f"Test flour {run_id}",
            item_type="ingredient",
            base_unit_code="g",
            purchase_unit_code="kg",
        ))
        db.flush()
        db.add(inventory_models.InventoryLocationItem(
            id=location_item_a,
            organization_id=test_actors.organization_id,
            location_id=test_actors.location_a,
            inventory_item_id=item_a,
        ))
        db.add(inventory_models.InventoryLocationItem(
            id=item_a_other_location,
            organization_id=test_actors.organization_id,
            location_id=test_actors.location_b,
            inventory_item_id=item_a,
        ))
        db.execute(text("SELECT set_config('app.organization_id', :org, true)"), {"org": str(test_actors.other_organization)})
        db.execute(text("SELECT set_config('app.location_ids', :locations, true)"), {"locations": str(test_actors.other_location)})
        db.add(inventory_models.InventoryCategory(id=category_b, organization_id=test_actors.other_organization, name=f"Other-{run_id}"))
        db.add(inventory_models.InventoryItem(
            id=item_b,
            organization_id=test_actors.other_organization,
            category_id=category_b,
            sku=f"OTHER-{run_id}",
            name=f"Other tenant item {run_id}",
            item_type="ingredient",
            base_unit_code="g",
            purchase_unit_code="kg",
        ))
        db.flush()
        db.add(inventory_models.InventoryLocationItem(
            id=location_item_b,
            organization_id=test_actors.other_organization,
            location_id=test_actors.other_location,
            inventory_item_id=item_b,
        ))
    engine.dispose()
    return InventoryFixture(item_a, item_b, category_a, category_b, location_item_a, location_item_b, item_a_other_location)


@pytest.fixture
def inventory_fixture(test_actors):
    return make_inventory_fixture(test_actors)


def set_scope(connection, organization_id=None, location_ids=(), user_id=None, can_read_all=False):
    settings = {
        "app.organization_id": str(organization_id) if organization_id else "",
        "app.location_ids": ",".join(str(location_id) for location_id in location_ids),
        "app.user_id": str(user_id) if user_id else "",
        "app.can_read_all_locations": "true" if can_read_all else "false",
    }
    for key, value in settings.items():
        connection.execute(text("SELECT set_config(:key, :value, true)"), {"key": key, "value": value})


def movement_insert(connection, actors, fixture, *, idempotency_key, movement_id=None):
    movement_id = movement_id or uuid.uuid4()
    return connection.execute(text("""
        INSERT INTO stock_movements (
            id, organization_id, location_id, inventory_item_id, movement_type,
            quantity_delta, unit_code, idempotency_key, actor_id
        ) VALUES (:id, :org, :location, :item, 'receiving', 250.000000, 'g', :key, :actor)
    """), {
        "id": movement_id,
        "org": actors.organization_id,
        "location": actors.location_a,
        "item": fixture.item_a,
        "key": idempotency_key,
        "actor": actors.owner_id,
    })


def test_inventory_rows_are_isolated_by_organization_and_location(app_connection, test_actors, inventory_fixture):
    set_scope(app_connection, test_actors.organization_id, [test_actors.location_a], test_actors.owner_id)
    assert set(app_connection.scalars(select(inventory_models.InventoryItem.id))) == {inventory_fixture.item_a}
    assert set(app_connection.scalars(select(inventory_models.InventoryLocationItem.location_id))) == {test_actors.location_a}
    assert app_connection.execute(
        text("SELECT count(*) FROM inventory_location_items WHERE location_id = :id"),
        {"id": test_actors.location_b},
    ).scalar_one() == 0

    set_scope(app_connection, test_actors.organization_id, [test_actors.location_a], test_actors.owner_id, can_read_all=True)
    assert set(app_connection.scalars(select(inventory_models.InventoryLocationItem.location_id))) == {
        test_actors.location_a,
        test_actors.location_b,
    }

    set_scope(app_connection, test_actors.other_organization, [test_actors.other_location], test_actors.owner_id)
    assert set(app_connection.scalars(select(inventory_models.InventoryItem.id))) == {inventory_fixture.item_b}
    assert set(app_connection.scalars(select(inventory_models.InventoryLocationItem.location_id))) == {test_actors.other_location}


def test_inventory_rls_fails_closed_without_tenant_or_location_context(app_connection, test_actors, inventory_fixture):
    set_scope(app_connection)
    assert app_connection.execute(text("SELECT count(*) FROM inventory_items")).scalar_one() == 0
    assert app_connection.execute(text("SELECT count(*) FROM inventory_location_items")).scalar_one() == 0

    set_scope(app_connection, test_actors.organization_id, [])
    assert app_connection.execute(text("SELECT count(*) FROM inventory_location_items")).scalar_one() == 0
    assert app_connection.execute(text("SELECT count(*) FROM stock_movements")).scalar_one() == 0


def test_inventory_rls_blocks_cross_scope_writes(app_connection, test_actors, inventory_fixture):
    set_scope(app_connection, test_actors.organization_id, [test_actors.location_a], test_actors.owner_id)
    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            app_connection.execute(text("""
                INSERT INTO inventory_location_items (id, organization_id, location_id, inventory_item_id, active)
                VALUES (:id, :org, :other_location, :item, true)
            """), {
                "id": uuid.uuid4(),
                "org": test_actors.organization_id,
                "other_location": test_actors.location_b,
                "item": inventory_fixture.item_a,
            })
    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            app_connection.execute(text("""
                INSERT INTO inventory_categories (id, organization_id, name)
                VALUES (:id, :other_org, :name)
            """), {"id": uuid.uuid4(), "other_org": test_actors.other_organization, "name": f"denied-{uuid.uuid4().hex}"})


def test_stock_movement_is_append_only_and_actor_scoped(app_connection, test_actors, inventory_fixture):
    set_scope(app_connection, test_actors.organization_id, [test_actors.location_a], test_actors.owner_id)
    movement_insert(app_connection, test_actors, inventory_fixture, idempotency_key=f"opening-{uuid.uuid4()}")
    assert app_connection.execute(text("""
        SELECT has_table_privilege(current_user, 'stock_movements', 'UPDATE')
            OR has_table_privilege(current_user, 'stock_movements', 'DELETE')
            OR has_table_privilege(current_user, 'stock_movements', 'TRUNCATE')
    """)).scalar_one() is False
    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            app_connection.execute(text("UPDATE stock_movements SET quantity_delta = 999 WHERE inventory_item_id = :id"), {"id": inventory_fixture.item_a})

    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            app_connection.execute(text("SELECT set_config('app.user_id', '', true)"))
            movement_insert(app_connection, test_actors, inventory_fixture, idempotency_key=f"wrong-actor-{uuid.uuid4()}")


def test_movement_idempotency_key_is_unique(app_connection, test_actors, inventory_fixture):
    set_scope(app_connection, test_actors.organization_id, [test_actors.location_a], test_actors.owner_id)
    key = f"retry-{uuid.uuid4()}"
    movement_insert(app_connection, test_actors, inventory_fixture, idempotency_key=key)
    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            movement_insert(app_connection, test_actors, inventory_fixture, idempotency_key=key)


def test_ledger_mutation_trigger_blocks_fixture_administrator(test_actors, inventory_fixture):
    engine = create_engine(TEST_FIXTURE_DATABASE_URL)
    movement_id = uuid.uuid4()
    key = f"immutable-{uuid.uuid4()}"
    with engine.connect() as connection:
        transaction = connection.begin()
        set_scope(connection, test_actors.organization_id, [test_actors.location_a], test_actors.owner_id)
        movement_insert(connection, test_actors, inventory_fixture, idempotency_key=key, movement_id=movement_id)
        for statement in (
            "UPDATE stock_movements SET quantity_delta = 500 WHERE id = :id",
            "DELETE FROM stock_movements WHERE id = :id",
            "TRUNCATE stock_movements",
        ):
            with pytest.raises(DBAPIError):
                with connection.begin_nested():
                    connection.execute(text(statement), {"id": movement_id}) if ":id" in statement else connection.execute(text(statement))
        transaction.rollback()
    engine.dispose()


def test_role_permissions_are_seeded_for_inventory_workflow(app_connection):
    rows = app_connection.execute(text("""
        SELECT r.name, p.key
        FROM role_permissions rp
        JOIN roles r ON r.id = rp.role_id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE p.key LIKE 'inventory:%'
    """)).all()
    permissions = {(role, key) for role, key in rows}
    assert ("Corporate Owner", "inventory:read") in permissions
    assert ("Corporate Owner", "inventory:catalog:manage") in permissions
    assert ("General Manager", "inventory:approve") in permissions
    assert ("General Manager", "inventory:count") in permissions
    assert ("Employee", "inventory:count") in permissions
    assert ("Employee", "inventory:approve") not in permissions
