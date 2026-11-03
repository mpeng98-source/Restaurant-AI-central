from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_liveness_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_identity_and_location_endpoints_reject_unauthorized_requests():
    for path in ("/api/v1/me", "/api/v1/locations", "/api/v1/locations/00000000-0000-0000-0000-000000000002/dashboard"):
        response = client.get(path)
        assert response.status_code == 401, path


def test_public_registration_route_does_not_exist():
    assert client.post("/api/v1/auth/register", json={"email": "public@example.test"}).status_code == 404
