"""Role-based access control tests (acceptance tests 1 and 4)."""

from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def test_anonymous_gets_401_on_protected_endpoints(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/admin/users").status_code == 401
    assert client.post("/api/auth/logout").status_code == 401


def test_invalid_or_garbage_token_gets_401(client):
    response = client.get("/api/auth/me", headers=auth_headers("not-a-real-token"))
    assert response.status_code == 401
    malformed = client.get("/api/auth/me", headers={"Authorization": "Bearer"})
    assert malformed.status_code in (401, 403)


def test_donor_rejected_from_admin_endpoints_403(client, donor_token):
    response = client.get("/api/admin/users", headers=auth_headers(donor_token))
    assert response.status_code == 403
    assert "permission" in response.json()["detail"]


def test_organization_rejected_from_admin_endpoints_403(client, org_token):
    response = client.get("/api/admin/users", headers=auth_headers(org_token))
    assert response.status_code == 403


def test_admin_can_list_users(client, admin_token):
    response = client.get(
        "/api/admin/users", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    emails = [item["email"] for item in body["items"]]
    assert "admin@seva.example" in emails


def test_admin_users_endpoint_supports_pagination(client, admin_token):
    paged = client.get(
        "/api/admin/users",
        params={"page": 1, "page_size": 2},
        headers=auth_headers(admin_token),
    )
    assert paged.status_code == 200
    body = paged.json()
    assert len(body["items"]) <= 2
    assert body["page"] == 1 and body["page_size"] == 2
