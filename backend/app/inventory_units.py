"""Decimal-safe conversion helpers for inventory quantities.

Physical conversions are allowed only when both units share a declared dimension.
Packaging and vendor pack sizes use an explicit item-specific factor instead of
assuming that a case, bag, or bottle has a universal size.
"""

from decimal import Decimal

from app.inventory_models import InventoryUnit


def convert_quantity(quantity: Decimal, from_unit: InventoryUnit, to_unit: InventoryUnit) -> Decimal:
    """Convert using persisted base factors without rounding or float arithmetic."""

    if not isinstance(quantity, Decimal):
        raise TypeError("Inventory quantities must be Decimal values")
    if from_unit.dimension != to_unit.dimension:
        raise ValueError(f"Cannot convert {from_unit.dimension} to {to_unit.dimension}")
    return quantity * from_unit.factor_to_base / to_unit.factor_to_base


def convert_item_quantity(quantity: Decimal, factor_to_stock_unit: Decimal) -> Decimal:
    """Convert an explicitly configured item unit into that item's stock unit."""

    if not isinstance(quantity, Decimal) or not isinstance(factor_to_stock_unit, Decimal):
        raise TypeError("Inventory quantities and conversion factors must be Decimal values")
    if factor_to_stock_unit <= 0:
        raise ValueError("Item-specific conversion factor must be positive")
    return quantity * factor_to_stock_unit


def normalize_stock_quantity(quantity: Decimal, factor: Decimal) -> Decimal:
    """Match PostgreSQL numeric round(..., 6), including half-away-from-zero.

    Preview/reconciliation arithmetic must agree with persisted ledger arithmetic.
    The stock schema supports 18 integer digits and six fractional digits.
    """
    from decimal import ROUND_HALF_UP, localcontext
    if not isinstance(quantity, Decimal) or not isinstance(factor, Decimal):
        raise TypeError('Quantities and factors must be Decimal')
    if not quantity.is_finite() or not factor.is_finite() or factor <= 0:
        raise ValueError('Finite quantities and a positive finite factor required')
    with localcontext() as context:
        context.prec = 80
        result = (quantity * factor).quantize(Decimal('0.000001'),rounding=ROUND_HALF_UP)
    if abs(result) > Decimal('999999999999999999.999999'):
        raise ValueError('Converted quantity exceeds stock precision')
    return result
