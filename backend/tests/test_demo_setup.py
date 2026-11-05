import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from app import demo_setup
from app.demo_setup import DemoAccounts, TestAccount as SyntheticAccount


def test_demo_account_input_rejects_real_addresses_and_unknown_fields():
    for email in ("employee@restaurant.com", "employee@demo.example.evil", "bad address@demo.example"):
        with pytest.raises(ValidationError):
            SyntheticAccount(email=email, password="D7" + "x" * 40)
    with pytest.raises(ValidationError):
        SyntheticAccount(email="employee@demo.example", password="D7" + "x" * 40, role="Owner")


@pytest.mark.postgres
def test_demo_setup_uses_restricted_role_and_never_overwrites(monkeypatch, api_client):
    from conftest import TEST_DATABASE_URL
    if not TEST_DATABASE_URL:
        pytest.skip("Real PostgreSQL required")
    monkeypatch.setattr(demo_setup, "NAMESPACE", uuid.uuid4())
    monkeypatch.setattr(demo_setup.settings, "environment", "internal-demo")
    accounts = DemoAccounts.model_validate({key: {"email": f"{key}-{uuid.uuid4().hex}@demo.example",
                                                "password": "D7" + uuid.uuid4().hex}
                                           for key in ("owner", "gm", "employee")})
    result = demo_setup.setup(accounts)
    with pytest.raises(ValueError, match="already exists"):
        demo_setup.setup(accounts)
    response = api_client.post("/api/v1/auth/login", json=accounts.employee.model_dump())
    assert response.status_code == 200
    locations = api_client.get("/api/v1/inventory/locations").json()
    assert [row["id"] for row in locations] == [result["location_id"]]
    for key in ("second_location_id", "other_location_id"):
        assert api_client.get(f"/api/v1/inventory/locations/{result[key]}/catalog").status_code == 403
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM inventory_items")).scalar_one() == 0
    engine.dispose()
