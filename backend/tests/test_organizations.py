"""Organization application and verification tests (authorization cases 1-10)."""

from tests.conftest import (
    TEST_STORAGE,
    apply_organization,
    admin_verify,
    get_or_register,
    get_org_id,
    make_pdf_bytes,
)


def test_organization_submits_application(client):
    token = get_or_register(client, "apply1@example.com", "OrgPass12345", "organization", "Apply One")
    response = apply_organization(client, token, name="Seva Trust M3")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["verification_status"] == "pending_verification"
    assert body["name"] == "Seva Trust M3"
    assert body["verified_at"] is None


def test_application_initially_pending_and_visible_to_owner(client):
    token = get_or_register(client, "apply2@example.com", "OrgPass12345", "organization", "Apply Two")
    apply_organization(client, token)
    response = client.get(
        "/api/organizations/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["verification_status"] == "pending_verification"


def test_duplicate_application_conflict(client):
    token = get_or_register(client, "apply3@example.com", "OrgPass12345", "organization", "Apply Three")
    first = apply_organization(client, token)
    assert first.status_code == 201
    second = apply_organization(client, token)
    assert second.status_code == 409


def test_admin_approves_application(client, admin_token):
    token = get_or_register(client, "apply4@example.com", "OrgPass12345", "organization", "Apply Four")
    apply_organization(client, token)
    organization_id = get_org_id(client, token)
    response = admin_verify(client, admin_token, organization_id)
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] == "verified"
    assert body["verified_at"] is not None
    assert body["rejection_reason"] is None


def test_admin_rejects_with_reason(client, admin_token):
    token = get_or_register(client, "apply5@example.com", "OrgPass12345", "organization", "Apply Five")
    apply_organization(client, token)
    organization_id = get_org_id(client, token)
    response = client.post(
        f"/api/organizations/admin/{organization_id}/reject",
        json={"reason": "Address could not be verified"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] == "rejected"
    assert body["rejection_reason"] == "Address could not be verified"


def test_reject_without_reason_rejected(client, admin_token):
    token = get_or_register(client, "apply6@example.com", "OrgPass12345", "organization", "Apply Six")
    apply_organization(client, token)
    organization_id = get_org_id(client, token)
    response = client.post(
        f"/api/organizations/admin/{organization_id}/reject",
        json={"reason": "  "},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422


def test_non_admin_cannot_verify_or_reject(client, donor_token):
    token = get_or_register(client, "apply7@example.com", "OrgPass12345", "organization", "Apply Seven")
    apply_organization(client, token)
    organization_id = get_org_id(client, token)
    for path, payload in (
        (f"/api/organizations/admin/{organization_id}/verify", None),
        (f"/api/organizations/admin/{organization_id}/reject", {"reason": "nope"}),
    ):
        donor_response = client.post(
            path, json=payload, headers={"Authorization": f"Bearer {donor_token}"}
        )
        assert donor_response.status_code == 403
        org_response = client.post(
            path, json=payload, headers={"Authorization": f"Bearer {token}"}
        )
        assert org_response.status_code == 403


def test_unverified_organization_cannot_create_needs(client):
    token = get_or_register(client, "apply8@example.com", "OrgPass12345", "organization", "Apply Eight")
    apply_organization(client, token)
    response = client.post(
        "/api/needs",
        json={
            "category_id": "00000000-0000-0000-0000-000000000000",
            "title": "Should not be allowed",
            "unit": "pieces",
            "quantity_required": 5,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert "verified" in response.json()["detail"]


def test_organization_cannot_see_another_application(client, admin_token):
    from tests.conftest import get_or_register

    token = get_or_register(client, "apply13@example.com", "OrgPass12345", "organization", "Apply Thirteen")
    other_token = get_or_register(
        client, "org2@example.com", "Org2Pass12345", "organization", "Org2 Owner"
    )
    apply_organization(client, token, name="First Org")
    own_id = get_org_id(client, token)

    other_me = client.get(
        "/api/organizations/me", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert other_me.status_code == 404  # no application of its own

    other_doc = client.get(
        f"/api/organizations/{own_id}/verification-document",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other_doc.status_code == 404  # another org cannot fetch the document

    other_detail = client.get(
        f"/api/organizations/{own_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other_detail.status_code in (403, 404)

    # Admin sees the document; owner sees it; anonymous does not.
    admin_doc = client.get(
        f"/api/organizations/{own_id}/verification-document",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_doc.status_code == 200
    assert admin_doc.content.startswith(b"%PDF")
    owner_doc = client.get(
        f"/api/organizations/{own_id}/verification-document",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert owner_doc.status_code == 200
    anon_doc = client.get(f"/api/organizations/{own_id}/verification-document")
    assert anon_doc.status_code == 401


def test_verification_document_rejects_invalid_format(client):
    token = get_or_register(client, "apply9@example.com", "OrgPass12345", "organization", "Apply Nine")
    response = apply_organization(
        client,
        token,
        doc_bytes=b"this is not a pdf or image at all",
        filename="fake.pdf",
    )
    assert response.status_code == 422
    assert "Unsupported document type" in response.json()["detail"]
    # No application row was created by the failed attempt.
    me = client.get(
        "/api/organizations/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 404


def test_verification_document_rejects_oversized(client):
    token = get_or_register(client, "apply10@example.com", "OrgPass12345", "organization", "Apply Ten")
    big = make_pdf_bytes() + b"\x00" * (10 * 1024 * 1024)
    response = apply_organization(client, token, doc_bytes=big)
    assert response.status_code == 422
    assert "10 MB" in response.json()["detail"]


def test_verification_document_stored_outside_web_root(client):
    token = get_or_register(client, "apply11@example.com", "OrgPass12345", "organization", "Apply Eleven")
    apply_organization(client, token)
    verification_files = list((TEST_STORAGE / "verification").rglob("*"))
    files = [f for f in verification_files if f.is_file()]
    assert files, "document not stored"
    assert all("storage" in str(f) for f in files)  # under STORAGE_DIR only


def test_admin_lists_and_filters_applications(client, admin_token):
    token = get_or_register(client, "apply12@example.com", "OrgPass12345", "organization", "Apply Twelve")
    apply_organization(client, token, name="FilterOrg ABC")
    response = client.get(
        "/api/organizations/admin/all",
        params={"status": "pending_verification"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    names = [item["name"] for item in response.json()["items"]]
    assert "FilterOrg ABC" in names


def test_application_requires_organization_role(client, donor_token):
    response = apply_organization(client, donor_token)
    assert response.status_code == 403
