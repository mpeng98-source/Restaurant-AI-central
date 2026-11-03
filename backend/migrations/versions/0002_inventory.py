"""Add tenant-scoped inventory catalog and append-only stock ledger.

Revision ID: 0002_inventory
Revises: 0001_foundation
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from decimal import Decimal


revision = "0002_inventory"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


UNITS = sa.table(
    "inventory_units",
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("dimension", sa.String),
    sa.column("factor_to_base", sa.Numeric),
    sa.column("base_unit", sa.Boolean),
)


def upgrade() -> None:
    # Composite FKs below make it impossible to attach one tenant's item to
    # another tenant's location even if application validation is bypassed.
    op.create_unique_constraint("uq_locations_org_id_id", "locations", ["organization_id", "id"])

    op.create_table(
        "inventory_units",
        sa.Column("code", sa.String(24), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("dimension", sa.String(24), nullable=False),
        sa.Column("factor_to_base", sa.Numeric(30, 12), nullable=False),
        sa.Column("base_unit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("factor_to_base > 0", name="ck_inventory_units_factor_positive"),
    )
    op.bulk_insert(
        UNITS,
        [
            {"code": "ea", "name": "each", "dimension": "count", "factor_to_base": Decimal("1"), "base_unit": True},
            {"code": "g", "name": "gram", "dimension": "mass", "factor_to_base": Decimal("1"), "base_unit": True},
            {"code": "kg", "name": "kilogram", "dimension": "mass", "factor_to_base": Decimal("1000"), "base_unit": False},
            {"code": "oz", "name": "ounce", "dimension": "mass", "factor_to_base": Decimal("28.349523125"), "base_unit": False},
            {"code": "lb", "name": "pound", "dimension": "mass", "factor_to_base": Decimal("453.59237"), "base_unit": False},
            {"code": "ml", "name": "milliliter", "dimension": "volume", "factor_to_base": Decimal("1"), "base_unit": True},
            {"code": "l", "name": "liter", "dimension": "volume", "factor_to_base": Decimal("1000"), "base_unit": False},
            {"code": "tsp", "name": "teaspoon", "dimension": "volume", "factor_to_base": Decimal("4.92892159375"), "base_unit": False},
            {"code": "tbsp", "name": "tablespoon", "dimension": "volume", "factor_to_base": Decimal("14.78676478125"), "base_unit": False},
            {"code": "cup", "name": "cup", "dimension": "volume", "factor_to_base": Decimal("236.5882365"), "base_unit": False},
            {"code": "fl_oz", "name": "fluid ounce", "dimension": "volume", "factor_to_base": Decimal("29.5735295625"), "base_unit": False},
        ],
    )

    op.create_table(
        "inventory_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "id", name="uq_inventory_categories_org_id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_inventory_categories_org_name"),
        sa.ForeignKeyConstraint(
            ["organization_id", "parent_id"], ["inventory_categories.organization_id", "inventory_categories.id"],
            name="fk_inventory_categories_parent_same_org",
        ),
    )
    op.create_index("ix_inventory_categories_organization_id", "inventory_categories", ["organization_id"])

    op.create_table(
        "inventory_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("barcode", sa.String(80), nullable=True),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("item_type", sa.String(24), nullable=False),
        sa.Column("base_unit_code", sa.String(24), nullable=False),
        sa.Column("purchase_unit_code", sa.String(24), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "id", name="uq_inventory_items_org_id"),
        sa.UniqueConstraint("organization_id", "sku", name="uq_inventory_items_org_sku"),
        sa.CheckConstraint("item_type IN ('ingredient', 'packaging', 'finished_good', 'menu_product')", name="ck_inventory_items_type"),
        sa.ForeignKeyConstraint(
            ["organization_id", "category_id"], ["inventory_categories.organization_id", "inventory_categories.id"],
            name="fk_inventory_items_category_same_org",
        ),
        sa.ForeignKeyConstraint(["base_unit_code"], ["inventory_units.code"], name="fk_inventory_items_base_unit"),
        sa.ForeignKeyConstraint(["purchase_unit_code"], ["inventory_units.code"], name="fk_inventory_items_purchase_unit"),
    )
    op.create_index("ix_inventory_items_organization_id", "inventory_items", ["organization_id"])

    op.create_table(
        "inventory_vendors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("vendor_code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("organization_id", "id", name="uq_inventory_vendors_org_id"),
        sa.UniqueConstraint("organization_id", "vendor_code", name="uq_inventory_vendors_code"),
    )
    op.create_index("ix_inventory_vendors_organization_id", "inventory_vendors", ["organization_id"])

    op.create_table(
        "inventory_storage_zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("organization_id", "id", name="uq_inventory_zones_org_id"),
        sa.UniqueConstraint("organization_id", "location_id", "id", name="uq_inventory_zones_scope_id"),
        sa.UniqueConstraint("organization_id", "location_id", "code", name="uq_inventory_zones_location_code"),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id"], ["locations.organization_id", "locations.id"],
            name="fk_inventory_zones_location_same_org",
        ),
    )
    op.create_index("ix_inventory_storage_zones_organization_id", "inventory_storage_zones", ["organization_id"])
    op.create_index("ix_inventory_storage_zones_location_id", "inventory_storage_zones", ["location_id"])

    op.create_table(
        "inventory_location_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inventory_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_zone_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("par_level", sa.Numeric(24, 6), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("organization_id", "location_id", "inventory_item_id", name="uq_inventory_location_item"),
        sa.CheckConstraint("par_level IS NULL OR par_level >= 0", name="ck_inventory_location_items_par_nonnegative"),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id"], ["locations.organization_id", "locations.id"],
            name="fk_inventory_location_items_location_same_org",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "inventory_item_id"], ["inventory_items.organization_id", "inventory_items.id"],
            name="fk_inventory_location_items_item_same_org",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id", "storage_zone_id"],
            ["inventory_storage_zones.organization_id", "inventory_storage_zones.location_id", "inventory_storage_zones.id"],
            name="fk_inventory_location_items_zone_same_location",
        ),
    )
    op.create_index("ix_inventory_location_items_organization_id", "inventory_location_items", ["organization_id"])
    op.create_index("ix_inventory_location_items_location_id", "inventory_location_items", ["location_id"])
    op.create_index("ix_inventory_location_items_inventory_item_id", "inventory_location_items", ["inventory_item_id"])

    op.create_table(
        "inventory_item_unit_conversions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inventory_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_code", sa.String(24), nullable=False),
        sa.Column("factor_to_stock_unit", sa.Numeric(30, 12), nullable=False),
        sa.UniqueConstraint("organization_id", "location_id", "inventory_item_id", "unit_code", name="uq_inventory_item_unit_conversion"),
        sa.CheckConstraint("factor_to_stock_unit > 0", name="ck_inventory_item_conversion_factor_positive"),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id", "inventory_item_id"],
            ["inventory_location_items.organization_id", "inventory_location_items.location_id", "inventory_location_items.inventory_item_id"],
            name="fk_inventory_item_conversion_location_item",
        ),
        sa.ForeignKeyConstraint(["unit_code"], ["inventory_units.code"], name="fk_inventory_item_conversion_unit"),
    )
    op.create_index("ix_inventory_item_unit_conversions_organization_id", "inventory_item_unit_conversions", ["organization_id"])
    op.create_index("ix_inventory_item_unit_conversions_location_id", "inventory_item_unit_conversions", ["location_id"])
    op.create_index("ix_inventory_item_unit_conversions_inventory_item_id", "inventory_item_unit_conversions", ["inventory_item_id"])

    op.create_table(
        "inventory_vendor_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inventory_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_sku", sa.String(80), nullable=True),
        sa.Column("purchase_unit_code", sa.String(24), nullable=False),
        sa.Column("pack_to_stock_factor", sa.Numeric(30, 12), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("organization_id", "location_id", "vendor_id", "inventory_item_id", name="uq_inventory_vendor_item_location"),
        sa.CheckConstraint("pack_to_stock_factor > 0", name="ck_inventory_vendor_items_factor_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_inventory_vendor_items_price_nonnegative"),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id"], ["locations.organization_id", "locations.id"],
            name="fk_inventory_vendor_items_location_same_org",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "vendor_id"], ["inventory_vendors.organization_id", "inventory_vendors.id"],
            name="fk_inventory_vendor_items_vendor_same_org",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "inventory_item_id"], ["inventory_items.organization_id", "inventory_items.id"],
            name="fk_inventory_vendor_items_item_same_org",
        ),
        sa.ForeignKeyConstraint(["purchase_unit_code"], ["inventory_units.code"], name="fk_inventory_vendor_items_unit"),
    )
    op.create_index("ix_inventory_vendor_items_organization_id", "inventory_vendor_items", ["organization_id"])
    op.create_index("ix_inventory_vendor_items_location_id", "inventory_vendor_items", ["location_id"])

    op.create_table(
        "inventory_count_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("organization_id", "location_id", "idempotency_key", name="uq_inventory_count_idempotency"),
        sa.UniqueConstraint("organization_id", "location_id", "id", name="uq_inventory_count_sessions_scope_id"),
        sa.CheckConstraint("status IN ('draft', 'submitted', 'approved', 'rejected')", name="ck_inventory_count_sessions_status"),
        sa.CheckConstraint("length(trim(idempotency_key)) > 0", name="ck_inventory_count_idempotency_nonempty"),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id"], ["locations.organization_id", "locations.id"],
            name="fk_inventory_count_sessions_location_same_org",
        ),
    )
    op.create_index("ix_inventory_count_sessions_organization_id", "inventory_count_sessions", ["organization_id"])
    op.create_index("ix_inventory_count_sessions_location_id", "inventory_count_sessions", ["location_id"])

    op.create_table(
        "inventory_count_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inventory_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 6), nullable=False),
        sa.Column("unit_code", sa.String(24), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("photo_object_key", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "location_id", "id", name="uq_inventory_count_lines_scope_id"),
        sa.UniqueConstraint("organization_id", "location_id", "session_id", "inventory_item_id", name="uq_inventory_count_line_item"),
        sa.CheckConstraint("quantity >= 0", name="ck_inventory_count_lines_quantity_nonnegative"),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id", "session_id"],
            ["inventory_count_sessions.organization_id", "inventory_count_sessions.location_id", "inventory_count_sessions.id"],
            name="fk_inventory_count_lines_session_scope",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id", "inventory_item_id"],
            ["inventory_location_items.organization_id", "inventory_location_items.location_id", "inventory_location_items.inventory_item_id"],
            name="fk_inventory_count_lines_location_item",
        ),
        sa.ForeignKeyConstraint(["unit_code"], ["inventory_units.code"], name="fk_inventory_count_lines_unit"),
    )
    op.create_index("ix_inventory_count_lines_organization_id", "inventory_count_lines", ["organization_id"])
    op.create_index("ix_inventory_count_lines_location_id", "inventory_count_lines", ["location_id"])

    op.create_table(
        "inventory_adjustment_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("count_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.UniqueConstraint("organization_id", "location_id", "count_line_id", name="uq_inventory_adjustment_approval_count_line"),
        sa.UniqueConstraint("organization_id", "location_id", "id", name="uq_inventory_approvals_scope_id"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_inventory_adjustment_approvals_status"),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id", "count_line_id"],
            ["inventory_count_lines.organization_id", "inventory_count_lines.location_id", "inventory_count_lines.id"],
            name="fk_inventory_approval_count_line_scope",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id"], ["locations.organization_id", "locations.id"],
            name="fk_inventory_approval_location_same_org",
        ),
    )
    op.create_index("ix_inventory_adjustment_approvals_organization_id", "inventory_adjustment_approvals", ["organization_id"])
    op.create_index("ix_inventory_adjustment_approvals_location_id", "inventory_adjustment_approvals", ["location_id"])

    op.create_table(
        "stock_movements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inventory_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("movement_type", sa.String(24), nullable=False),
        sa.Column("quantity_delta", sa.Numeric(24, 6), nullable=False),
        sa.Column("unit_code", sa.String(24), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=True),
        sa.Column("source_id", sa.String(128), nullable=True),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reverses_movement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approver_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "location_id", "idempotency_key", name="uq_stock_movements_idempotency"),
        sa.UniqueConstraint("organization_id", "location_id", "id", name="uq_stock_movements_scope_id"),
        sa.CheckConstraint(
            "movement_type IN ('opening', 'receiving', 'count_adjustment', 'waste', 'transfer_in', 'transfer_out', 'production_in', 'production_out', 'reversal')",
            name="ck_stock_movements_type",
        ),
        sa.CheckConstraint("quantity_delta <> 0", name="ck_stock_movements_nonzero"),
        sa.CheckConstraint("length(trim(idempotency_key)) > 0", name="ck_stock_movements_idempotency_nonempty"),
        sa.CheckConstraint(
            "(movement_type IN ('opening', 'receiving', 'transfer_in', 'production_in') AND quantity_delta > 0) "
            "OR (movement_type IN ('waste', 'transfer_out', 'production_out') AND quantity_delta < 0) "
            "OR movement_type IN ('count_adjustment', 'reversal')",
            name="ck_stock_movements_direction",
        ),
        sa.CheckConstraint("(movement_type = 'reversal') = (reverses_movement_id IS NOT NULL)", name="ck_stock_movements_reversal_reference"),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id"], ["locations.organization_id", "locations.id"],
            name="fk_stock_movements_location_same_org",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id", "inventory_item_id"],
            ["inventory_location_items.organization_id", "inventory_location_items.location_id", "inventory_location_items.inventory_item_id"],
            name="fk_stock_movements_location_item",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id", "approval_id"],
            ["inventory_adjustment_approvals.organization_id", "inventory_adjustment_approvals.location_id", "inventory_adjustment_approvals.id"],
            name="fk_stock_movements_approval_scope",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "location_id", "reverses_movement_id"],
            ["stock_movements.organization_id", "stock_movements.location_id", "stock_movements.id"],
            name="fk_stock_movements_reversal_scope",
        ),
        sa.ForeignKeyConstraint(["unit_code"], ["inventory_units.code"], name="fk_stock_movements_unit"),
    )
    op.create_index("ix_stock_movements_organization_id", "stock_movements", ["organization_id"])
    op.create_index("ix_stock_movements_location_id", "stock_movements", ["location_id"])
    op.create_index("ix_stock_movements_inventory_item_id", "stock_movements", ["inventory_item_id"])
    op.create_index(
        "uq_stock_movement_approval_once", "stock_movements", ["organization_id", "location_id", "approval_id"],
        unique=True, postgresql_where=sa.text("approval_id IS NOT NULL"),
    )
    op.create_index(
        "uq_stock_movement_reversal_once", "stock_movements", ["organization_id", "location_id", "reverses_movement_id"],
        unique=True, postgresql_where=sa.text("reverses_movement_id IS NOT NULL"),
    )
    op.create_index(
        "uq_stock_movement_opening_once", "stock_movements", ["organization_id", "location_id", "inventory_item_id"],
        unique=True, postgresql_where=sa.text("movement_type = 'opening'"),
    )

    _install_rls()
    _install_permissions()
    _install_ledger_guards()


def _install_rls() -> None:
    org_tables = ("inventory_categories", "inventory_items", "inventory_vendors")
    location_tables = (
        "inventory_storage_zones",
        "inventory_location_items",
        "inventory_item_unit_conversions",
        "inventory_vendor_items",
        "inventory_count_sessions",
        "inventory_count_lines",
        "inventory_adjustment_approvals",
        "stock_movements",
    )
    for table in org_tables + location_tables:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
    for table in org_tables:
        policy = "organization_id::text = current_setting('app.organization_id', true)"
        op.execute(sa.text(f"CREATE POLICY inventory_tenant_scope ON {table} USING ({policy}) WITH CHECK ({policy})"))
    for table in location_tables:
        assigned_scope = (
            "organization_id::text = current_setting('app.organization_id', true) "
            "AND location_id::text = ANY(string_to_array(current_setting('app.location_ids', true), ','))"
        )
        readable_scope = (
            "organization_id::text = current_setting('app.organization_id', true) AND "
            "(location_id::text = ANY(string_to_array(current_setting('app.location_ids', true), ',')) "
            "OR current_setting('app.can_read_all_locations', true) = 'true')"
        )
        op.execute(sa.text(f"CREATE POLICY inventory_location_read_scope ON {table} FOR SELECT USING ({readable_scope})"))
        if table != "stock_movements":
            op.execute(sa.text(f"CREATE POLICY inventory_location_write_scope ON {table} FOR ALL USING ({assigned_scope}) WITH CHECK ({assigned_scope})"))
        else:
            op.execute(sa.text(f"CREATE POLICY inventory_movement_insert_scope ON {table} FOR INSERT WITH CHECK ({assigned_scope})"))
    op.execute(sa.text("GRANT SELECT ON inventory_units TO chubby_app"))
    op.execute(sa.text("REVOKE INSERT, UPDATE, DELETE ON inventory_units FROM chubby_app"))
    op.execute(sa.text("REVOKE UPDATE, DELETE ON stock_movements FROM chubby_app"))
    op.execute(sa.text("REVOKE TRUNCATE ON stock_movements FROM chubby_app"))


def _install_permissions() -> None:
    permissions = (
        ("inventory:read", "Read inventory catalog and authorized location stock"),
        ("inventory:count", "Create and submit inventory counts at an assigned location"),
        ("inventory:approve", "Review and decide inventory adjustments at an assigned location"),
        ("inventory:catalog:manage", "Manage organization inventory master data"),
    )
    for key, description in permissions:
        op.execute(
            sa.text("INSERT INTO permissions (id, key, description) VALUES (gen_random_uuid(), :key, :description) ON CONFLICT (key) DO NOTHING")
            .bindparams(key=key, description=description)
        )
    role_permissions = {
        "Corporate Owner": ("inventory:read", "inventory:catalog:manage"),
        "General Manager": ("inventory:read", "inventory:count", "inventory:approve", "inventory:catalog:manage"),
        "Employee": ("inventory:read", "inventory:count"),
    }
    for role_name, keys in role_permissions.items():
        for key in keys:
            op.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT r.id, p.id FROM roles r CROSS JOIN permissions p "
                    "WHERE r.name = :role_name AND p.key = :permission_key ON CONFLICT DO NOTHING"
                ).bindparams(role_name=role_name, permission_key=key)
            )


def _install_ledger_guards() -> None:
    op.execute(sa.text("""
        CREATE FUNCTION prevent_stock_movement_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'stock movements are append-only; create a reversal movement';
        END
        $$
    """))
    op.execute(sa.text("""
        CREATE TRIGGER stock_movements_append_only
        BEFORE UPDATE OR DELETE ON stock_movements
        FOR EACH ROW EXECUTE FUNCTION prevent_stock_movement_mutation()
    """))
    op.execute(sa.text("""
        CREATE TRIGGER stock_movements_no_truncate
        BEFORE TRUNCATE ON stock_movements
        FOR EACH STATEMENT EXECUTE FUNCTION prevent_stock_movement_mutation()
    """))
    op.execute(sa.text("""
        CREATE FUNCTION validate_stock_movement_insert() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE approval_status text;
        expected_unit text;
        original_item uuid;
        original_quantity numeric;
        BEGIN
            IF NEW.actor_id::text IS DISTINCT FROM current_setting('app.user_id', true) THEN
                RAISE EXCEPTION 'stock movement actor must match the authenticated user context';
            END IF;
            SELECT base_unit_code INTO expected_unit
            FROM inventory_items
            WHERE id = NEW.inventory_item_id AND organization_id = NEW.organization_id;
            IF expected_unit IS NULL OR NEW.unit_code IS DISTINCT FROM expected_unit THEN
                RAISE EXCEPTION 'stock movement quantity must use the inventory item base unit';
            END IF;
            IF NEW.movement_type = 'count_adjustment' THEN
                SELECT status INTO approval_status
                FROM inventory_adjustment_approvals
                WHERE id = NEW.approval_id
                  AND organization_id = NEW.organization_id
                  AND location_id = NEW.location_id;
                IF NEW.approval_id IS NULL OR approval_status IS DISTINCT FROM 'approved' OR NEW.approver_id IS NULL THEN
                    RAISE EXCEPTION 'count adjustments require an approved location adjustment';
                END IF;
            END IF;
            IF NEW.movement_type = 'reversal' THEN
                SELECT inventory_item_id, quantity_delta INTO original_item, original_quantity
                FROM stock_movements
                WHERE id = NEW.reverses_movement_id
                  AND organization_id = NEW.organization_id
                  AND location_id = NEW.location_id;
                IF original_item IS NULL OR original_item IS DISTINCT FROM NEW.inventory_item_id
                    OR NEW.quantity_delta IS DISTINCT FROM -original_quantity THEN
                    RAISE EXCEPTION 'reversal must exactly offset its referenced movement';
                END IF;
            END IF;
            RETURN NEW;
        END
        $$
    """))
    op.execute(sa.text("""
        CREATE TRIGGER stock_movements_validate_insert
        BEFORE INSERT ON stock_movements
        FOR EACH ROW EXECUTE FUNCTION validate_stock_movement_insert()
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS stock_movements_validate_insert ON stock_movements"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS stock_movements_no_truncate ON stock_movements"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS stock_movements_append_only ON stock_movements"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS validate_stock_movement_insert()"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_stock_movement_mutation()"))
    for key in ("inventory:read", "inventory:count", "inventory:approve", "inventory:catalog:manage"):
        op.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE key = :key)").bindparams(key=key))
        op.execute(sa.text("DELETE FROM permissions WHERE key = :key").bindparams(key=key))
    for table in (
        "stock_movements",
        "inventory_adjustment_approvals",
        "inventory_count_lines",
        "inventory_count_sessions",
        "inventory_vendor_items",
        "inventory_item_unit_conversions",
        "inventory_location_items",
        "inventory_storage_zones",
        "inventory_vendors",
        "inventory_items",
        "inventory_categories",
        "inventory_units",
    ):
        op.drop_table(table)
    op.drop_constraint("uq_locations_org_id_id", "locations", type_="unique")
