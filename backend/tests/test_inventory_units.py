from decimal import Decimal, Inexact, Rounded, localcontext

import pytest

from app.inventory_units import convert_item_quantity, convert_quantity
from app.inventory_models import InventoryUnit
from app.db import Base


def unit(code: str, dimension: str, factor: str) -> InventoryUnit:
    return InventoryUnit(
        code=code,
        name=code,
        dimension=dimension,
        factor_to_base=Decimal(factor),
        base_unit=False,
    )


def test_mass_and_volume_conversions_use_decimal_factors():
    assert convert_quantity(Decimal("1.25"), unit("kg", "mass", "1000"), unit("g", "mass", "1")) == Decimal("1250.00")
    assert convert_quantity(Decimal("2"), unit("cup", "volume", "236.5882365"), unit("ml", "volume", "1")) == Decimal("473.1764730")


def test_conversion_rejects_incompatible_dimensions_and_binary_float():
    with pytest.raises(ValueError, match="Cannot convert mass to volume"):
        convert_quantity(Decimal("1"), unit("g", "mass", "1"), unit("ml", "volume", "1"))
    with pytest.raises(TypeError, match="Decimal"):
        convert_quantity(1.0, unit("g", "mass", "1"), unit("g", "mass", "1"))  # type: ignore[arg-type]


def test_item_pack_conversion_requires_positive_explicit_factor():
    assert convert_item_quantity(Decimal("2"), Decimal("6")) == Decimal("12")
    with pytest.raises(ValueError, match="must be positive"):
        convert_item_quantity(Decimal("2"), Decimal("0"))


def test_item_specific_case_conversion_returns_decimal_pieces():
    with localcontext() as context:
        context.clear_flags()
        pieces = convert_item_quantity(Decimal("3"), Decimal("12"))

        assert not context.flags[Inexact]
        assert not context.flags[Rounded]

    assert isinstance(pieces, Decimal)
    assert pieces == Decimal("36")


def test_inventory_models_do_not_expand_the_immutable_foundation_metadata():
    assert "inventory_items" not in Base.metadata.tables
    assert "stock_movements" not in Base.metadata.tables


def test_stock_rounding_matches_postgresql_and_rejects_overflow():
    from app.inventory_units import normalize_stock_quantity
    assert normalize_stock_quantity(Decimal('0.0000005'),Decimal('1'))==Decimal('0.000001')
    assert normalize_stock_quantity(Decimal('-0.0000005'),Decimal('1'))==Decimal('-0.000001')
    with pytest.raises(ValueError,match='precision'):
        normalize_stock_quantity(Decimal('999999999999999999.999999'),Decimal('1000'))
    with pytest.raises(ValueError,match='Finite'):
        normalize_stock_quantity(Decimal('NaN'),Decimal('1'))
