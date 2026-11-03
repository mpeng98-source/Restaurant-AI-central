import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class InventoryBase(DeclarativeBase):
    """Separate metadata keeps new tables out of the immutable 0001 migration."""


class InventoryCategory(InventoryBase):
    """Organization-owned catalog grouping; inventory is shared across its locations."""

    __tablename__ = "inventory_categories"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_inventory_categories_org_id"),
        UniqueConstraint("organization_id", "name", name="uq_inventory_categories_org_name"),
        ForeignKeyConstraint(
            ["organization_id", "parent_id"],
            ["inventory_categories.organization_id", "inventory_categories.id"],
            name="fk_inventory_categories_parent_same_org",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InventoryUnit(InventoryBase):
    """Global unit catalog. Item-specific conversions are stored on scoped records."""

    __tablename__ = "inventory_units"
    __table_args__ = (
        CheckConstraint("factor_to_base > 0", name="ck_inventory_units_factor_positive"),
    )

    code: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    dimension: Mapped[str] = mapped_column(String(24), nullable=False)
    factor_to_base: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    base_unit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class InventoryItem(InventoryBase):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_inventory_items_org_id"),
        UniqueConstraint("organization_id", "sku", name="uq_inventory_items_org_sku"),
        ForeignKeyConstraint(
            ["organization_id", "category_id"],
            ["inventory_categories.organization_id", "inventory_categories.id"],
            name="fk_inventory_items_category_same_org",
        ),
        ForeignKeyConstraint(["base_unit_code"], ["inventory_units.code"], name="fk_inventory_items_base_unit"),
        ForeignKeyConstraint(["purchase_unit_code"], ["inventory_units.code"], name="fk_inventory_items_purchase_unit"),
        CheckConstraint(
            "item_type IN ('ingredient', 'packaging', 'finished_good', 'menu_product')",
            name="ck_inventory_items_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    item_type: Mapped[str] = mapped_column(String(24), nullable=False)
    base_unit_code: Mapped[str] = mapped_column(String(24), nullable=False)
    purchase_unit_code: Mapped[str] = mapped_column(String(24), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InventoryStorageZone(InventoryBase):
    __tablename__ = "inventory_storage_zones"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_inventory_zones_org_id"),
        UniqueConstraint("organization_id", "location_id", "id", name="uq_inventory_zones_scope_id"),
        UniqueConstraint("organization_id", "location_id", "code", name="uq_inventory_zones_location_code"),
        ForeignKeyConstraint(
            ["organization_id", "location_id"],
            ["locations.organization_id", "locations.id"],
            name="fk_inventory_zones_location_same_org",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class InventoryLocationItem(InventoryBase):
    """An organization's inventory item enabled at one restaurant location."""

    __tablename__ = "inventory_location_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "location_id", "inventory_item_id", name="uq_inventory_location_item"),
        ForeignKeyConstraint(
            ["organization_id", "location_id"],
            ["locations.organization_id", "locations.id"],
            name="fk_inventory_location_items_location_same_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "inventory_item_id"],
            ["inventory_items.organization_id", "inventory_items.id"],
            name="fk_inventory_location_items_item_same_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "location_id", "storage_zone_id"],
            ["inventory_storage_zones.organization_id", "inventory_storage_zones.location_id", "inventory_storage_zones.id"],
            name="fk_inventory_location_items_zone_same_location",
        ),
        CheckConstraint("par_level IS NULL OR par_level >= 0", name="ck_inventory_location_items_par_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    storage_zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    par_level: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class InventoryItemUnitConversion(InventoryBase):
    """Explicit location-specific item unit to stock-unit conversion."""

    __tablename__ = "inventory_item_unit_conversions"
    __table_args__ = (
        UniqueConstraint("organization_id", "location_id", "inventory_item_id", "unit_code", name="uq_inventory_item_unit_conversion"),
        ForeignKeyConstraint(
            ["organization_id", "location_id", "inventory_item_id"],
            ["inventory_location_items.organization_id", "inventory_location_items.location_id", "inventory_location_items.inventory_item_id"],
            name="fk_inventory_item_conversion_location_item",
        ),
        ForeignKeyConstraint(["unit_code"], ["inventory_units.code"], name="fk_inventory_item_conversion_unit"),
        CheckConstraint("factor_to_stock_unit > 0", name="ck_inventory_item_conversion_factor_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    unit_code: Mapped[str] = mapped_column(String(24), nullable=False)
    factor_to_stock_unit: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)


class InventoryVendor(InventoryBase):
    __tablename__ = "inventory_vendors"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_inventory_vendors_org_id"),
        UniqueConstraint("organization_id", "vendor_code", name="uq_inventory_vendors_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    vendor_code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class InventoryVendorItem(InventoryBase):
    __tablename__ = "inventory_vendor_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "location_id", "vendor_id", "inventory_item_id", name="uq_inventory_vendor_item_location"),
        ForeignKeyConstraint(
            ["organization_id", "location_id"],
            ["locations.organization_id", "locations.id"],
            name="fk_inventory_vendor_items_location_same_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "vendor_id"],
            ["inventory_vendors.organization_id", "inventory_vendors.id"],
            name="fk_inventory_vendor_items_vendor_same_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "inventory_item_id"],
            ["inventory_items.organization_id", "inventory_items.id"],
            name="fk_inventory_vendor_items_item_same_org",
        ),
        ForeignKeyConstraint(["purchase_unit_code"], ["inventory_units.code"], name="fk_inventory_vendor_items_unit"),
        CheckConstraint("pack_to_stock_factor > 0", name="ck_inventory_vendor_items_factor_positive"),
        CheckConstraint("unit_price >= 0", name="ck_inventory_vendor_items_price_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vendor_sku: Mapped[str | None] = mapped_column(String(80))
    purchase_unit_code: Mapped[str] = mapped_column(String(24), nullable=False)
    pack_to_stock_factor: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class InventoryCountSession(InventoryBase):
    __tablename__ = "inventory_count_sessions"
    __table_args__ = (
        UniqueConstraint("organization_id", "location_id", "idempotency_key", name="uq_inventory_count_idempotency"),
        UniqueConstraint("organization_id", "location_id", "id", name="uq_inventory_count_sessions_scope_id"),
        ForeignKeyConstraint(
            ["organization_id", "location_id"],
            ["locations.organization_id", "locations.id"],
            name="fk_inventory_count_sessions_location_same_org",
        ),
        CheckConstraint("status IN ('draft', 'submitted', 'approved', 'rejected')", name="ck_inventory_count_sessions_status"),
        CheckConstraint("length(trim(idempotency_key)) > 0", name="ck_inventory_count_idempotency_nonempty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InventoryCountLine(InventoryBase):
    __tablename__ = "inventory_count_lines"
    __table_args__ = (
        UniqueConstraint("organization_id", "location_id", "id", name="uq_inventory_count_lines_scope_id"),
        UniqueConstraint("organization_id", "location_id", "session_id", "inventory_item_id", name="uq_inventory_count_line_item"),
        ForeignKeyConstraint(
            ["organization_id", "location_id", "session_id"],
            ["inventory_count_sessions.organization_id", "inventory_count_sessions.location_id", "inventory_count_sessions.id"],
            name="fk_inventory_count_lines_session_scope",
        ),
        ForeignKeyConstraint(
            ["organization_id", "location_id", "inventory_item_id"],
            ["inventory_location_items.organization_id", "inventory_location_items.location_id", "inventory_location_items.inventory_item_id"],
            name="fk_inventory_count_lines_location_item",
        ),
        ForeignKeyConstraint(["unit_code"], ["inventory_units.code"], name="fk_inventory_count_lines_unit"),
        CheckConstraint("quantity >= 0", name="ck_inventory_count_lines_quantity_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    photo_object_key: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InventoryAdjustmentApproval(InventoryBase):
    __tablename__ = "inventory_adjustment_approvals"
    __table_args__ = (
        UniqueConstraint("organization_id", "location_id", "count_line_id", name="uq_inventory_adjustment_approval_count_line"),
        UniqueConstraint("organization_id", "location_id", "id", name="uq_inventory_approvals_scope_id"),
        ForeignKeyConstraint(
            ["organization_id", "location_id", "count_line_id"],
            ["inventory_count_lines.organization_id", "inventory_count_lines.location_id", "inventory_count_lines.id"],
            name="fk_inventory_approval_count_line_scope",
        ),
        ForeignKeyConstraint(
            ["organization_id", "location_id"],
            ["locations.organization_id", "locations.id"],
            name="fk_inventory_approval_location_same_org",
        ),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_inventory_adjustment_approvals_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    count_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)


class StockMovement(InventoryBase):
    """Append-only signed quantity delta in the inventory item's base unit."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        UniqueConstraint("organization_id", "location_id", "idempotency_key", name="uq_stock_movements_idempotency"),
        UniqueConstraint("organization_id", "location_id", "id", name="uq_stock_movements_scope_id"),
        ForeignKeyConstraint(
            ["organization_id", "location_id"],
            ["locations.organization_id", "locations.id"],
            name="fk_stock_movements_location_same_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "location_id", "inventory_item_id"],
            ["inventory_location_items.organization_id", "inventory_location_items.location_id", "inventory_location_items.inventory_item_id"],
            name="fk_stock_movements_location_item",
        ),
        ForeignKeyConstraint(
            ["organization_id", "location_id", "approval_id"],
            ["inventory_adjustment_approvals.organization_id", "inventory_adjustment_approvals.location_id", "inventory_adjustment_approvals.id"],
            name="fk_stock_movements_approval_scope",
        ),
        ForeignKeyConstraint(
            ["organization_id", "location_id", "reverses_movement_id"],
            ["stock_movements.organization_id", "stock_movements.location_id", "stock_movements.id"],
            name="fk_stock_movements_reversal_scope",
        ),
        ForeignKeyConstraint(["unit_code"], ["inventory_units.code"], name="fk_stock_movements_unit"),
        CheckConstraint(
            "movement_type IN ('opening', 'receiving', 'count_adjustment', 'waste', 'transfer_in', 'transfer_out', 'production_in', 'production_out', 'reversal')",
            name="ck_stock_movements_type",
        ),
        CheckConstraint("quantity_delta <> 0", name="ck_stock_movements_nonzero"),
        CheckConstraint("length(trim(idempotency_key)) > 0", name="ck_stock_movements_idempotency_nonempty"),
        CheckConstraint(
            "(movement_type IN ('opening', 'receiving', 'transfer_in', 'production_in') AND quantity_delta > 0) "
            "OR (movement_type IN ('waste', 'transfer_out', 'production_out') AND quantity_delta < 0) "
            "OR movement_type IN ('count_adjustment', 'reversal')",
            name="ck_stock_movements_direction",
        ),
        CheckConstraint("(movement_type = 'reversal') = (reverses_movement_id IS NOT NULL)", name="ck_stock_movements_reversal_reference"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    movement_type: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(40))
    source_id: Mapped[str | None] = mapped_column(String(128))
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reverses_movement_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    approver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
