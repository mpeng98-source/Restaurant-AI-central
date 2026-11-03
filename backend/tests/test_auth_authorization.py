from datetime import datetime, timedelta, timezone
import secrets

import pytest
from sqlalchemy import create_engine, select, update, text
from sqlalchemy.orm import Session

import app.models as models
from app.security import token_hash
from conftest import TEST_MIGRATION_DATABASE_URL


def login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    assert response.json()["csrf_token"]
    return response


@pytest.mark.postgres
def test_owner_gm_employee_can_authenticate_and_receive_secure_sessions(api_client, test_actors):
    for email in (test_actors.owner_email, test_actors.gm_email, test_actors.employee_email):
        response = login(api_client, email, test_actors.password)
        session_cookie = response.headers.get_list("set-cookie")
        assert any("chubby_session=" in value and "httponly" in value.lower() and "secure" in value.lower() and "samesite=strict" in value.lower() for value in session_cookie)
        assert any("chubby_csrf=" in value and "httponly" not in value.lower() and "secure" in value.lower() for value in session_cookie)
        assert api_client.get("/api/v1/me").status_code == 200
        api_client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": response.json()["csrf_token"]})
        assert api_client.get("/api/v1/me").status_code == 401
        api_client.cookies.clear()


@pytest.mark.postgres
def test_login_rejects_bad_password_and_rate_limits(api_client, test_actors):
    bad_password = secrets.token_urlsafe(32)
    for _ in range(5):
        response = api_client.post("/api/v1/auth/login", json={"email": test_actors.gm_email, "password": bad_password})
        assert response.status_code == 401
    response = api_client.post("/api/v1/auth/login", json={"email": test_actors.gm_email, "password": bad_password})
    assert response.status_code == 429


@pytest.mark.postgres
def test_invitation_is_required_single_use_and_creates_employee(api_client, test_actors):
    response = login(api_client, test_actors.owner_email, test_actors.password)
    csrf = response.json()["csrf_token"]
    assert api_client.post("/api/v1/auth/register", json={"email": "public@example.test"}).status_code == 404
    created = api_client.post("/api/v1/auth/invitations", json={
        "email": "invited@example.test", "role": "Employee", "location_ids": [str(test_actors.location_a)],
    }, headers={"X-CSRF-Token": csrf})
    assert created.status_code == 201, created.text
    token = created.json()["token"]
    invited_password = secrets.token_urlsafe(32)
    body = {"token": token, "first_name": "Invited", "last_name": "Employee", "password": invited_password}
    accepted = api_client.post("/api/v1/auth/invitations/accept", json=body)
    assert accepted.status_code == 201, accepted.text
    assert api_client.post("/api/v1/auth/invitations/accept", json=body).status_code == 400
    api_client.cookies.clear()
    assert api_client.post("/api/v1/auth/login", json={"email": "invited@example.test", "password": body["password"]}).status_code == 200
    me = api_client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["employee"] == {"first_name": "Invited", "last_name": "Employee"}


@pytest.mark.postgres
def test_owner_invites_general_manager_who_accepts_and_is_scoped(api_client, test_actors):
    owner_login = login(api_client, test_actors.owner_email, test_actors.password)
    invite = api_client.post(
        "/api/v1/auth/invitations",
        json={"email": "invited-gm@example.test", "role": "General Manager", "location_ids": [str(test_actors.location_b)]},
        headers={"X-CSRF-Token": owner_login.json()["csrf_token"]},
    )
    assert invite.status_code == 201, invite.text
    gm_password = secrets.token_urlsafe(32)
    accept = api_client.post("/api/v1/auth/invitations/accept", json={
        "token": invite.json()["token"], "first_name": "Invited", "last_name": "Manager", "password": gm_password,
    })
    assert accept.status_code == 201, accept.text
    assert api_client.post("/api/v1/auth/invitations/accept", json={
        "token": invite.json()["token"], "first_name": "Invited", "last_name": "Manager", "password": gm_password,
    }).status_code == 400
    api_client.cookies.clear()
    manager_login = login(api_client, "invited-gm@example.test", gm_password)
    assert manager_login.status_code == 200
    assert api_client.get(f"/api/v1/locations/{test_actors.location_b}/dashboard").status_code == 200
    assert api_client.get(f"/api/v1/locations/{test_actors.location_a}/dashboard").status_code == 403
    assert api_client.get(f"/api/v1/locations/{test_actors.other_location}/dashboard").status_code == 403


@pytest.mark.postgres
def test_owner_gm_and_employee_location_permissions(api_client, test_actors):
    login(api_client, test_actors.owner_email, test_actors.password)
    assert api_client.get(f"/api/v1/locations/{test_actors.location_a}/dashboard").status_code == 200
    assert api_client.get(f"/api/v1/locations/{test_actors.location_b}/dashboard").status_code == 200
    assert api_client.get(f"/api/v1/locations/{test_actors.other_location}/dashboard").status_code == 403
    owner_locations = {row["id"] for row in api_client.get("/api/v1/locations").json()}
    assert str(test_actors.location_a) in owner_locations and str(test_actors.location_b) in owner_locations

    api_client.cookies.clear()
    gm_login = login(api_client, test_actors.gm_email, test_actors.password)
    assert api_client.get(f"/api/v1/locations/{test_actors.location_a}/dashboard").status_code == 200
    invite_attempt = api_client.post("/api/v1/auth/invitations", json={"email": "forbidden@example.test", "role": "Employee", "location_ids": [str(test_actors.location_a)]}, headers={"X-CSRF-Token": gm_login.json()["csrf_token"]})
    assert invite_attempt.status_code == 403
    assert api_client.get(f"/api/v1/locations/{test_actors.location_b}/dashboard").status_code == 403
    assert api_client.get(f"/api/v1/locations/{test_actors.other_location}/dashboard").status_code == 403
    assert api_client.get(f"/api/v1/locations/{test_actors.location_a}/employees").status_code == 200

    api_client.cookies.clear()
    login(api_client, test_actors.employee_email, test_actors.password)
    assert api_client.get("/api/v1/me").json()["employee"]["first_name"] == "Test"
    assert api_client.get(f"/api/v1/locations/{test_actors.location_a}/dashboard").status_code == 403
    assert api_client.get(f"/api/v1/locations/{test_actors.location_a}/employees").status_code == 403
    assert api_client.get(f"/api/v1/locations/{test_actors.location_b}/dashboard").status_code == 403
    assert api_client.get("/api/v1/locations").json() == []


@pytest.mark.postgres
def test_session_expiration_and_csrf_protection(api_client, test_actors):
    response = login(api_client, test_actors.gm_email, test_actors.password)
    assert api_client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    session_token = api_client.cookies.get("chubby_session")
    engine = create_engine(TEST_MIGRATION_DATABASE_URL)
    with Session(engine) as db, db.begin():
        db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(test_actors.gm_id)})
        db.execute(update(models.Session).where(models.Session.token_hash == token_hash(session_token)).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    engine.dispose()
    assert api_client.get("/api/v1/me").status_code == 401


@pytest.mark.postgres
def test_password_reset_token_expiry_is_enforced(api_client, test_actors):
    reset = api_client.post("/api/v1/auth/password-reset/request", json={"email": test_actors.employee_email})
    assert reset.status_code == 202
    token = reset.json().get("development_token")
    assert token
    engine = create_engine(TEST_MIGRATION_DATABASE_URL)
    with Session(engine) as db, db.begin():
        db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(test_actors.employee_id)})
        db.execute(update(models.PasswordResetToken).where(models.PasswordResetToken.token_hash == token_hash(token)).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    engine.dispose()
    rejected = api_client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "password": secrets.token_urlsafe(32)})
    assert rejected.status_code == 400


@pytest.mark.postgres
def test_password_reset_token_is_expiring_single_use_and_revokes_sessions(api_client, test_actors):
    login(api_client, test_actors.employee_email, test_actors.password)
    reset = api_client.post("/api/v1/auth/password-reset/request", json={"email": test_actors.employee_email})
    assert reset.status_code == 202
    token = reset.json().get("development_token")
    assert token
    new_password = secrets.token_urlsafe(32)
    updated = api_client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "password": new_password})
    assert updated.status_code == 200
    assert api_client.get("/api/v1/me").status_code == 401
    assert api_client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "password": new_password}).status_code == 400
    api_client.cookies.clear()
    assert api_client.post("/api/v1/auth/login", json={"email": test_actors.employee_email, "password": new_password}).status_code == 200
