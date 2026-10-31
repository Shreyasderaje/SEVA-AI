"""Needs management tests (authorization cases 11-18)."""

from tests.conftest import (
    admin_verify,
    apply_organization,
    category_ids,
    create_need,
    get_org_id,
    get_or_register,
)


def _verified_org(client, admin_token, email, name):
    token = get_or_register(
        client, email, "OrgPass12345", "organization", f"{name} Owner"
    )
    applied = apply_organization(client, token, name=name)
    assert applied.status_code in (201, 409), applied.text
    admin_verify(client, admin_token, get_org_id(client, token))
    return token


def test_verified_organization_creates_need(client, admin_token):
    token = _verified_org(client, admin_token, "needs1@example.com", "Needs Org One")
    response = create_need(
        client, token, title="Blankets for winter", category_code="clothing"
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "active"
    assert body["quantity_required"] == 20.0
    assert body["quantity_fulfilled"] == 0.0
    assert body["remaining_quantity"] == 20.0
    assert body["category_code"] == "clothing"


def test_organization_edits_own_need(client, admin_token):
    token = _verified_org(client, admin_token, "needs2@example.com", "Needs Org Two")
    created = create_need(client, token, title="Original title")
    need_id = created.json()["id"]

    response = client.patch(
        f"/api/needs/{need_id}",
        json={"title": "Updated title", "urgency": "critical"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Updated title"
    assert body["urgency"] == "critical"


def test_organization_cannot_edit_another_needs(client, admin_token):
    token_a = _verified_org(client, admin_token, "needs3@example.com", "Needs Org Three")
    token_b = _verified_org(client, admin_token, "needs4@example.com", "Needs Org Four")
    created = create_need(client, token_a, title="Org A need")
    need_id = created.json()["id"]

    response = client.patch(
        f"/api/needs/{need_id}",
        json={"title": "Hijacked"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404

    delete_attempt = client.post(
        f"/api/needs/{need_id}/fulfilment",
        json={"quantity": 1},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert delete_attempt.status_code == 404


def test_invalid_quantity_rejected(client, admin_token):
    token = _verified_org(client, admin_token, "needs5@example.com", "Needs Org Five")
    zero = create_need(client, token, quantity_required="0")
    assert zero.status_code == 422
    negative = create_need(client, token, quantity_required="-5")
    assert negative.status_code == 422


def test_fulfilled_cannot_exceed_required(client, admin_token):
    token = _verified_org(client, admin_token, "needs6@example.com", "Needs Org Six")
    created = create_need(client, token, quantity_required="10")
    need_id = created.json()["id"]
    headers = {"Authorization": f"Bearer {token}"}

    ok = client.post(
        f"/api/needs/{need_id}/fulfilment", json={"quantity": 6}, headers=headers
    )
    assert ok.status_code == 200
    over = client.post(
        f"/api/needs/{need_id}/fulfilment", json={"quantity": 5}, headers=headers
    )
    assert over.status_code == 422
    assert "cannot exceed" in over.json()["detail"]
    # Exactly the remaining amount succeeds and auto-fulfils.
    rest = client.post(
        f"/api/needs/{need_id}/fulfilment", json={"quantity": 4}, headers=headers
    )
    assert rest.status_code == 200
    assert rest.json()["status"] == "fulfilled"
    assert rest.json()["remaining_quantity"] == 0


def test_fulfilled_need_excluded_from_matching(client, admin_token):
    from tests.conftest import create_donation

    token = _verified_org(client, admin_token, "needs7@example.com", "Needs Org Seven")
    donor_token = get_or_register(
        client, "matchdonor1@example.com", "DonorPass123", "donor", "Match Donor"
    )
    need = create_need(
        client, token, title="Fulfilled need test", category_code="clothing"
    )
    need_id = need.json()["id"]
    headers = {"Authorization": f"Bearer {token}"}
    fulfilled = client.post(
        f"/api/needs/{need_id}/fulfilment", json={"quantity": 20}, headers=headers
    )
    assert fulfilled.status_code == 200, fulfilled.text

    donation = create_donation(client, donor_token, title="Clothing for matching")
    matches = client.get(
        f"/api/donations/{donation.json()['id']}/matches",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert matches.status_code == 200
    org_ids = [m["organization_id"] for m in matches.json()["eligible"]]
    org_id = get_org_id(client, token)
    assert org_id not in org_ids
    reasons = {e["reason_code"] for e in matches.json()["excluded"]}
    # An auto-fulfilled need is inactive OR fully funded depending on timing.
    assert reasons & {"need_fully_funded", "need_not_active"}


def test_paused_need_excluded_from_matching(client, admin_token):
    from tests.conftest import create_donation

    token = _verified_org(client, admin_token, "needs8@example.com", "Needs Org Eight")
    donor_token = get_or_register(
        client, "matchdonor2@example.com", "DonorPass123", "donor", "Match Donor Two"
    )
    need = create_need(
        client, token, title="Paused need test", category_code="utensils", status="paused"
    )
    assert need.json()["status"] == "paused"

    donation = create_donation(client, donor_token, category_code="utensils")
    matches = client.get(
        f"/api/donations/{donation.json()['id']}/matches",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    org_ids = [m["organization_id"] for m in matches.json()["eligible"]]
    assert get_org_id(client, token) not in org_ids


def test_remaining_quantity_calculated_correctly(client, admin_token):
    token = _verified_org(client, admin_token, "needs9@example.com", "Needs Org Nine")
    created = create_need(client, token, quantity_required="12.5", unit="kg")
    need_id = created.json()["id"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        f"/api/needs/{need_id}/fulfilment", json={"quantity": 2.5}, headers=headers
    )
    detail = client.get(f"/api/needs/{need_id}", headers=headers)
    body = detail.json()
    assert body["quantity_fulfilled"] == 2.5
    assert body["remaining_quantity"] == 10.0


def test_status_transitions_validated(client, admin_token):
    token = _verified_org(client, admin_token, "needs10@example.com", "Needs Org Ten")
    created = create_need(client, token, title="Transition need")
    need_id = created.json()["id"]
    headers = {"Authorization": f"Bearer {token}"}

    paused = client.post(
        f"/api/needs/{need_id}/status", json={"status": "paused"}, headers=headers
    )
    assert paused.status_code == 200
    resumed = client.post(
        f"/api/needs/{need_id}/status", json={"status": "active"}, headers=headers
    )
    assert resumed.status_code == 200
    closed = client.post(
        f"/api/needs/{need_id}/status", json={"status": "closed"}, headers=headers
    )
    assert closed.status_code == 200
    reopen = client.post(
        f"/api/needs/{need_id}/status", json={"status": "active"}, headers=headers
    )
    assert reopen.status_code == 409  # closed is terminal


def test_public_needs_listing_shows_verified_only(client, admin_token, org_token):
    apply_organization(client, org_token, name="Unverified Public Org")
    unverified_token = org_token
    create_need(client, unverified_token, title="Should not appear")  # 403, nothing created

    token = _verified_org(client, admin_token, "needs11@example.com", "Public Verified Org")
    create_need(client, token, title="Public verified need", category_code="clothing")

    response = client.get("/api/needs/public")
    assert response.status_code == 200
    titles = [n["title"] for n in response.json()]
    assert "Public verified need" in titles
    assert "Should not appear" not in titles


def test_subcategory_must_match_category(client, admin_token):
    token = _verified_org(client, admin_token, "needs12@example.com", "Needs Org Twelve")
    categories = category_ids(client)
    clothing = next(c for c in client.get("/api/categories").json() if c["code"] == "clothing")
    grains_sub = next(
        c for c in client.get("/api/categories").json() if c["code"] == "grains_rice"
    )["subcategories"][0]["id"]
    response = client.post(
        "/api/needs",
        json={
            "category_id": clothing["id"],
            "subcategory_id": grains_sub,
            "title": "Mismatched subcategory",
            "unit": "pieces",
            "quantity_required": 5,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


import pytest

pytestmark = pytest.mark.usefixtures("clean_orgs")
