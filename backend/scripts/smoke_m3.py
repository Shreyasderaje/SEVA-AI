"""M3 live smoke test: organization application -> admin verification -> needs
CRUD -> eligibility + matching. Run against the live backend:

    cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8010
    .venv/Scripts/python.exe scripts/smoke_m3.py http://localhost:8010
"""

import io
import sys
import time

import httpx
from PIL import Image

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8010"


def jpeg_bytes(color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color=color).save(buf, "JPEG")
    return buf.getvalue()


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=60)
    stamp = int(time.time())

    # 1. Register an organization user and submit an application (with PDF).
    reg = client.post(
        "/api/auth/register",
        json={"email": f"m3.org.{stamp}@example.com", "password": "M3OrgPass1",
              "full_name": "M3 Org Owner", "role": "organization"},
    )
    assert reg.status_code == 201, reg.text
    org_token = reg.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {org_token}"

    bad_doc = client.post(
        "/api/organizations/apply",
        data={"name": "Bad Doc Org", "location_consent": "false"},
        files=[("document", ("v.pdf", b"not a pdf", "application/pdf"))],
    )
    print("invalid document rejected:", bad_doc.status_code)
    assert bad_doc.status_code == 422

    apply_response = client.post(
        "/api/organizations/apply",
        data={
            "name": "M3 Hope Charitable Trust",
            "org_type": "ngo",
            "description": "Stage-1 M3 smoke org.",
            "address": "1 Verification Way",
            "contact_email": f"m3.org.{stamp}@example.org",
            "representative_name": "Rep Person",
            "latitude": "12.9716",
            "longitude": "77.5946",
            "location_consent": "true",
        },
        files=[("document", ("registration.pdf", b"%PDF-1.4 smoke test document", "application/pdf"))],
    )
    print("apply:", apply_response.status_code, apply_response.json()["verification_status"])
    assert apply_response.status_code == 201
    org_id = apply_response.json()["id"]

    # 2. Unverified org cannot create needs.
    early = client.post(
        "/api/needs",
        json={"category_id": "00000000-0000-0000-0000-000000000000", "title": "Too early",
              "unit": "pieces", "quantity_required": 5},
    )
    print("unverified need creation blocked:", early.status_code)
    assert early.status_code == 403

    # 3. Admin verifies; org document accessible to owner + admin only.
    admin = client.post(
        "/api/auth/login",
        json={"email": "admin@seva.example", "password": "1ykp9qHPtWtJnyyi"},
    )
    assert admin.status_code == 200
    admin_token = admin.json()["access_token"]
    doc_owner = client.get(f"/api/organizations/{org_id}/verification-document")
    print("owner document fetch:", doc_owner.status_code, doc_owner.content[:5])
    assert doc_owner.status_code == 200 and doc_owner.content.startswith(b"%PDF")

    donor_reg = client.post(
        "/api/auth/register",
        json={"email": f"m3.donor.{stamp}@example.com", "password": "M3DonorPass1",
              "full_name": "M3 Donor", "role": "donor"},
    )
    donor_token = donor_reg.json()["access_token"]
    doc_donor = httpx.get(
        f"{BASE}/api/organizations/{org_id}/verification-document",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    print("donor document fetch (expect 404):", doc_donor.status_code)
    assert doc_donor.status_code == 404

    verify = client.post(
        f"/api/organizations/admin/{org_id}/verify",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    print("admin verify:", verify.status_code, verify.json()["verification_status"])
    assert verify.status_code == 200

    # 4. Verified org creates a need (clothing, near the donation pickup area).
    categories = client.get("/api/categories").json()
    clothing = next(c for c in categories if c["code"] == "clothing")
    need = client.post(
        "/api/needs",
        json={"category_id": clothing["id"], "title": "Warm clothes for families",
              "unit": "pieces", "quantity_required": 30, "urgency": "critical",
              "required_by": str(time.strftime("%Y-%m-%d", time.localtime(time.time() + 5 * 86400)))},
    )
    print("create need:", need.status_code, need.json()["status"],
          "remaining:", need.json()["remaining_quantity"])
    assert need.status_code == 201
    need_id = need.json()["id"]

    # 5. Donor creates a donation nearby (same coordinates) and fetches matches.
    donor_client = httpx.Client(base_url=BASE, timeout=60)
    donor_client.headers["Authorization"] = f"Bearer {donor_token}"
    donation = donor_client.post(
        "/api/donations",
        data={"title": "Winter jackets bundle", "category_id": clothing["id"],
              "quantity": "15", "unit": "pieces", "pickup_area": "Central Library",
              "pickup_latitude": "12.9810", "pickup_longitude": "77.6000",
              "location_consent": "true"},
        files=[("images", ("photo.jpg", jpeg_bytes((200, 100, 50)), "image/jpeg"))],
    )
    print("donation:", donation.status_code, donation.json()["reference"])
    assert donation.status_code == 201
    donation_id = donation.json()["id"]

    matches = donor_client.get(f"/api/donations/{donation_id}/matches")
    body = matches.json()
    print("matches:", matches.status_code,
          "| eligible:", len(body["eligible"]),
          "| excluded:", body["excluded"])
    assert matches.status_code == 200
    assert len(body["eligible"]) == 1
    match = body["eligible"][0]
    print("  rank:", match["rank"], "| org:", match["organization_name"],
          "| score:", match["score"], "| distance:", match["distance_km"], "km")
    print("  factors:", {k: v["score"] for k, v in match["factors"].items()})
    print("  reasons:", match["reasons"])
    assert match["organization_id"] == org_id
    assert match["verification_status"] == "verified"
    assert match["distance_km"] is not None and match["distance_km"] < 5
    assert set(match["factors"]) == {"compatibility", "urgency", "distance", "quantity_fit", "timeliness"}

    determinism = donor_client.get(f"/api/donations/{donation_id}/matches").json()
    assert determinism == body, "matching is not deterministic!"
    print("determinism check: identical output on repeat run")

    # 6. Fulfilment tracking: fulfil fully -> excluded from matching afterwards.
    fulfil = client.post(
        f"/api/needs/{need_id}/fulfilment", json={"quantity": 30}
    )
    print("fulfil:", fulfil.status_code, fulfil.json()["status"])
    assert fulfil.status_code == 200 and fulfil.json()["status"] == "fulfilled"
    after = donor_client.get(f"/api/donations/{donation_id}/matches").json()
    assert after["eligible"] == []
    print("fulfilled need excluded from matching: OK")

    # 7. Public endpoints.
    public_orgs = httpx.get(f"{BASE}/api/organizations")
    public_needs = httpx.get(f"{BASE}/api/organizations/{org_id}/public-needs")
    print("public directory:", public_orgs.status_code,
          "| public needs:", public_needs.status_code, len(public_needs.json()))
    assert public_orgs.status_code == 200
    assert any(o["id"] == org_id for o in public_orgs.json())
    assert public_needs.json() == []  # need is fulfilled -> not listed publicly

    print("\nM3 SMOKE TEST: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
