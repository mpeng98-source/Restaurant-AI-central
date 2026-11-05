import uuid

import pytest
from pydantic import ValidationError

from app.inventory_approvals import DecisionBody, ReviewedLine, ReversalBody


def decision():
    return {"version": 1, "snapshot_hash": "a" * 64, "action": "approved",
            "reason": "Synthetic review", "idempotency_key": "synthetic-key",
            "reviewed_lines": [{"line_id": str(uuid.uuid4()), "verdict": "accepted"}]}


def test_decision_rejects_unknown_top_level_and_nested_fields():
    payload = decision()
    for candidate in ({**payload, "confirmed": True},
                      {**payload, "reviewed_lines": [{**payload["reviewed_lines"][0], "approved": True}]}):
        with pytest.raises(ValidationError) as error:
            DecisionBody.model_validate(candidate)
        assert any(item["type"] == "extra_forbidden" for item in error.value.errors())
    assert DecisionBody.model_validate(payload).action == "approved"


@pytest.mark.parametrize(("model", "payload"), [
    (ReviewedLine, {"line_id": str(uuid.uuid4()), "verdict": "accepted"}),
    (ReversalBody, {"idempotency_key": "synthetic-key", "reason": "Synthetic correction", "expected_balance": "315"}),
])
def test_review_and_reversal_models_reject_unknown_fields(model, payload):
    with pytest.raises(ValidationError) as error:
        model.model_validate({**payload, "unknown": "value"})
    assert error.value.errors()[0]["type"] == "extra_forbidden"
