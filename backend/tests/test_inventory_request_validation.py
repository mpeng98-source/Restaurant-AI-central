import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.inventory_counts import AssignmentBody, CountLineBody, CreateSession, VersionBody


@pytest.mark.parametrize(("model", "payload"), [
    (CreateSession, {"idempotency_key": "synthetic-key"}),
    (AssignmentBody, {"version": 1, "assigned_to": str(uuid.uuid4())}),
    (CountLineBody, {"version": 1, "sku": "TEST", "quantity": "0", "unit_code": "g"}),
    (VersionBody, {"version": 1}),
])
def test_count_request_models_reject_unknown_fields(model, payload):
    with pytest.raises(ValidationError) as error:
        model.model_validate({**payload, "percentge_threshold": "25"})
    assert any(item["type"] == "extra_forbidden" and item["loc"] == ("percentge_threshold",)
               for item in error.value.errors())


def test_create_threshold_defaults_and_explicit_decimal_values_are_preserved():
    default = CreateSession(idempotency_key="synthetic-key")
    assert default.quantity_threshold == Decimal("0")
    assert default.percentage_threshold == Decimal("5")
    explicit = CreateSession(idempotency_key="synthetic-key", percentage_threshold="25.000001")
    assert explicit.percentage_threshold == Decimal("25.000001")


def test_count_request_rejects_float_and_nonfinite_thresholds():
    for threshold in (25.0, "NaN", "Infinity"):
        with pytest.raises(ValidationError):
            CreateSession(idempotency_key="synthetic-key", percentage_threshold=threshold)
