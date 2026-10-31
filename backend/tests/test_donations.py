"""Donation lifecycle tests: creation, image validation, status history,
ownership (IDOR), cancellation, dashboard summary, filters.

Covers master acceptance tests 5, 6 (partially — see test_classify for the
rest), and the M2 half of the addendum corrections #1/#4/#7.
"""

import re

from tests.conftest import (
    TEST_STORAGE,
    create_donation,
    make_jpeg_bytes,
    make_png_bytes,
    storage_file_count,
)

REFERENCE_PATTERN = re.compile(r"^SEVA-\d{4}-\d{6}$")


# ---------------------------------------------------------------- creation


def test_create_donation_with_single_image(client, donor_token):
    response = create_donation(client, donor_token)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert REFERENCE_PATTERN.match(body["reference"])
    assert body["category_code"] == "clothing"
    assert body["quantity"] == 5.0 and body["unit"] == "pieces"
    assert len(body["images"]) == 1
    assert body["images"][0]["position"] == 1
    assert body["timeline"] == [
        {"id": body["timeline"][0]["id"], "from_status": None, "to_status": "pending",
         "note": None, "created_at": body["timeline"][0]["created_at"]}
    ]


def test_create_donation_persists_reencoded_image_on_disk(client, donor_token):
    response = create_donation(client, donor_token, image_bytes=make_png_bytes())
    assert response.status_code == 201
    image = response.json()["images"][0]
    assert image["mime_type"] == "image/jpeg"  # PNG input re-encoded to JPEG

    stored = TEST_STORAGE / "donations"
    files = list(stored.rglob("*.jpg"))
    assert files, "no file written"
    # Re-encoding strips metadata: a fresh JPEG always starts with the JPEG magic.
    assert files[0].read_bytes()[:3] == b"\xff\xd8\xff"


def test_create_donation_with_three_images_positions_ordered(client, donor_token):
    response = create_donation(client, donor_token, image_count=3)
    assert response.status_code == 201
    positions = [img["position"] for img in response.json()["images"]]
    assert positions == [1, 2, 3]


def test_create_donation_stores_ai_suggestion_separately_from_confirmed(client, donor_token):
    response = create_donation(
        client,
        donor_token,
        category_code="utensils",  # donor's explicit choice
        ai_predicted="packaged_food",  # what the model suggested
        ai_confidence="0.86",
    )
    assert response.status_code == 201
    body = response.json()
    # The donor-confirmed category is the operative one (category_code);
    # the raw AI output is stored separately, never merged.
    assert body["category_code"] == "utensils"
    assert body["ai_predicted_category"] == "packaged_food"
    assert body["ai_confidence"] == 0.86


def test_create_donation_writes_exactly_one_history_row(client, donor_token):
    response = create_donation(client, donor_token)
    assert response.status_code == 201
    timeline = response.json()["timeline"]
    assert len(timeline) == 1
    assert timeline[0]["from_status"] is None
    assert timeline[0]["to_status"] == "pending"


def test_create_donation_files_use_uuid_names(client, donor_token):
    response = create_donation(client, donor_token, image_count=2)
    assert response.status_code == 201
    files = list((TEST_STORAGE / "donations").rglob("*.jpg"))
    names = {f.stem for f in files}
    assert all(len(name) == 32 for name in names)  # uuid4().hex
    assert len(names) >= 2


# ------------------------------------------------------------ validation (422)


def test_invalid_magic_bytes_rejected_with_no_file_left_behind(client, donor_token):
    before = storage_file_count()
    response = create_donation(
        client, donor_token, image_bytes=b"this is definitely not an image"
    )
    assert response.status_code == 422
    assert "Unsupported image type" in response.json()["detail"]
    assert storage_file_count() == before, "a file was left in storage"


def test_oversized_image_rejected(client, donor_token):
    before = storage_file_count()
    # Build a real JPEG over 5 MB (incompressible noise content).
    big = make_jpeg_bytes(size=(4000, 4000))
    # Guarantee the size regardless of compression:
    big = big + b"\x00" * (5 * 1024 * 1024)
    response = create_donation(client, donor_token, image_bytes=big)
    assert response.status_code == 422
    assert "5 MB" in response.json()["detail"]
    assert storage_file_count() == before


def test_four_images_rejected(client, donor_token):
    response = create_donation(client, donor_token, image_count=4)
    assert response.status_code == 422
    assert "1 and 3" in response.json()["detail"]


def test_zero_images_rejected(client, donor_token):
    token = donor_token
    categories = {c["code"]: c["id"] for c in client.get("/api/categories").json()}
    response = client.post(
        "/api/donations",
        data={
            "title": "No image donation",
            "category_id": categories["clothing"],
            "quantity": "2",
            "unit": "pieces",
            "pickup_area": "Somewhere",
        },
        files=[],
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_quantity_must_be_positive(client, donor_token):
    response = create_donation(client, donor_token, quantity="0")
    assert response.status_code == 422


def test_invalid_unit_rejected(client, donor_token):
    response = create_donation(
        client, donor_token, extra_fields={"unit": "tonnes"}
    )
    assert response.status_code == 422


def test_coordinates_require_explicit_consent(client, donor_token):
    response = create_donation(
        client, donor_token, lat="12.9716", lng="77.5946", consent="false"
    )
    assert response.status_code == 422
    assert "consent" in response.json()["detail"].lower()


def test_coordinate_ranges_validated(client, donor_token):
    response = create_donation(
        client, donor_token, lat="91", lng="77.5946", consent="true"
    )
    assert response.status_code == 422
    assert "Latitude" in response.json()["detail"]


def test_coordinates_without_longitude_rejected(client, donor_token):
    response = create_donation(client, donor_token, lat="12.9716", consent="true")
    assert response.status_code == 422


def test_ai_fields_must_come_together(client, donor_token):
    response = create_donation(client, donor_token, ai_predicted="clothing")
    assert response.status_code == 422
    assert "together" in response.json()["detail"]


def test_ai_predicted_must_be_a_fixed_class(client, donor_token):
    response = create_donation(
        client,
        donor_token,
        ai_predicted="furniture",
        ai_confidence="0.5",
    )
    assert response.status_code == 422


def test_unknown_category_rejected(client, donor_token):
    response = client.post(
        "/api/donations",
        data={
            "title": "Bad category donation",
            "category_id": "00000000-0000-0000-0000-000000000000",
            "quantity": "1",
            "unit": "pieces",
            "pickup_area": "Somewhere",
        },
        files=[("images", ("a.jpg", make_jpeg_bytes(), "image/jpeg"))],
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert response.status_code == 422


def test_title_too_short_rejected(client, donor_token):
    response = create_donation(client, donor_token, title="ab")
    assert response.status_code == 422


# -------------------------------------------------------------- roles / IDOR


def test_anonymous_cannot_create_donations(client):
    categories = {c["code"]: c["id"] for c in client.get("/api/categories").json()}
    response = client.post(
        "/api/donations",
        data={"title": "Anon donation", "category_id": categories["clothing"],
              "quantity": "1", "unit": "pieces", "pickup_area": "Area"},
        files=[("images", ("a.jpg", make_jpeg_bytes(), "image/jpeg"))],
    )
    assert response.status_code == 401


def test_organization_cannot_create_donations(client, org_token):
    response = create_donation(client, org_token)
    assert response.status_code == 403


def test_donor_cannot_view_another_donors_donation(client, donor_token, donor2_token):
    created = create_donation(client, donor_token)
    donation_id = created.json()["id"]

    response = client.get(
        f"/api/donations/{donation_id}",
        headers={"Authorization": f"Bearer {donor2_token}"},
    )
    assert response.status_code == 404  # 404: never reveal other users' donations


def test_admin_can_view_any_donation(client, donor_token, admin_token):
    created = create_donation(client, donor_token)
    donation_id = created.json()["id"]
    response = client.get(
        f"/api/donations/{donation_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == donation_id


def test_image_files_served_only_to_owner_or_admin(client, donor_token, donor2_token, admin_token):
    created = create_donation(client, donor_token)
    image_url = created.json()["images"][0]["url"]

    assert client.get(image_url).status_code == 401  # anonymous
    other = client.get(image_url, headers={"Authorization": f"Bearer {donor2_token}"})
    assert other.status_code == 404  # non-owner donor
    owner = client.get(image_url, headers={"Authorization": f"Bearer {donor_token}"})
    assert owner.status_code == 200
    assert owner.headers["content-type"].startswith("image/jpeg")
    admin = client.get(image_url, headers={"Authorization": f"Bearer {admin_token}"})
    assert admin.status_code == 200


# --------------------------------------------------------------- cancel


def test_donor_can_cancel_pending_donation(client, donor_token):
    created = create_donation(client, donor_token)
    donation_id = created.json()["id"]

    response = client.post(
        f"/api/donations/{donation_id}/cancel",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    statuses = [row["to_status"] for row in body["timeline"]]
    assert statuses == ["pending", "cancelled"]
    assert body["timeline"][1]["from_status"] == "pending"


def test_cannot_cancel_twice(client, donor_token):
    created = create_donation(client, donor_token)
    donation_id = created.json()["id"]
    first = client.post(
        f"/api/donations/{donation_id}/cancel",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/donations/{donation_id}/cancel",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert second.status_code == 409
    assert "pending or offered" in second.json()["detail"]


def test_cannot_cancel_another_donors_donation(client, donor_token, donor2_token):
    created = create_donation(client, donor_token)
    donation_id = created.json()["id"]
    response = client.post(
        f"/api/donations/{donation_id}/cancel",
        headers={"Authorization": f"Bearer {donor2_token}"},
    )
    assert response.status_code == 404


# ------------------------------------------------------- list / summary


def test_donor_list_returns_only_own_donations(client, donor_token, donor2_token):
    mine = create_donation(client, donor_token, title="Mine only jacket")
    assert mine.status_code == 201

    response = client.get(
        "/api/donations", headers={"Authorization": f"Bearer {donor2_token}"}
    )
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["items"]]
    assert "Mine only jacket" not in titles

    own = client.get(
        "/api/donations", headers={"Authorization": f"Bearer {donor_token}"}
    )
    assert "Mine only jacket" in [i["title"] for i in own.json()["items"]]


def test_list_filters_by_status_and_search(client, donor_token):
    created = create_donation(client, donor_token, title="UniqueRiceBag donation")
    donation_id = created.json()["id"]
    client.post(
        f"/api/donations/{donation_id}/cancel",
        headers={"Authorization": f"Bearer {donor_token}"},
    )

    cancelled = client.get(
        "/api/donations",
        params={"status": "cancelled", "q": "UniqueRiceBag"},
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert cancelled.status_code == 200
    items = cancelled.json()["items"]
    assert len(items) == 1 and items[0]["status"] == "cancelled"

    pending = client.get(
        "/api/donations",
        params={"status": "pending", "q": "UniqueRiceBag"},
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert pending.json()["items"] == []


def test_list_date_range_filter(client, donor_token):
    create_donation(client, donor_token, title="DateFilter jacket")
    import datetime as dt

    # created_at is stored in UTC while the filter takes local dates, so a
    # donation made just before local midnight can carry a UTC date one day
    # earlier: anchor the inclusive bound at yesterday to stay robust.
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()

    included = client.get(
        "/api/donations",
        params={"date_from": yesterday, "q": "DateFilter"},
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert included.json()["total"] >= 1

    excluded = client.get(
        "/api/donations",
        params={"date_from": tomorrow, "q": "DateFilter"},
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert excluded.json()["total"] == 0


def test_list_pagination(client, donor_token):
    for i in range(3):
        create_donation(client, donor_token, title=f"Pagination jacket {i}")
    response = client.get(
        "/api/donations",
        params={"page": 1, "page_size": 2, "q": "Pagination jacket"},
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1


def test_dashboard_summary_counts(client):
    # A fresh donor gives exact, isolated counts.
    from tests.conftest import get_or_register

    token = get_or_register(
        client, "summary-donor@example.com", "SummaryPass1", "donor", "Summary Donor"
    )
    headers = {"Authorization": f"Bearer {token}"}

    empty = client.get("/api/donations/summary", headers=headers).json()
    assert empty == {"active": 0, "accepted": 0, "completed": 0, "total": 0}

    first = create_donation(client, token, title="Summary jacket one")
    create_donation(client, token, title="Summary jacket two")
    counts = client.get("/api/donations/summary", headers=headers).json()
    assert counts["active"] == 2 and counts["total"] == 2

    client.post(
        f"/api/donations/{first.json()['id']}/cancel", headers=headers
    )
    counts = client.get("/api/donations/summary", headers=headers).json()
    assert counts["active"] == 1 and counts["total"] == 2
