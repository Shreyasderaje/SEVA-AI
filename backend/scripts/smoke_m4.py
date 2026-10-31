"""M4 live smoke test: sequential offers, accept/decline, pickup, completion,
notifications, and UPI payments. Run against the live backend:

    cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8010
    .venv/Scripts/python.exe scripts/smoke_m4.py http://localhost:8010
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
    admin_token = client.post(
        "/api/auth/login",
        json={"email": "admin@seva.example", "password": "M4SmokeAdmin1"},
    ).json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    def register(email, role, name):
        response = client.post(
            "/api/auth/register",
            json={"email": email, "password": "M4Pass1234", "full_name": name, "role": role},
        )
        if response.status_code == 409:
            response = client.post(
                "/api/auth/login", json={"email": email, "password": "M4Pass1234"}
            )
        return response.json()["access_token"]

    # Two verified orgs with clothing needs; donor with a clothing donation.
    org_a_token = register(f"m4.org.a.{stamp}@example.com", "organization", "M4 Org A")
    org_b_token = register(f"m4.org.b.{stamp}@example.com", "organization", "M4 Org B")
    donor_token = register(f"m4.donor.{stamp}@example.com", "donor", "M4 Donor")
    donor_headers = {"Authorization": f"Bearer {donor_token}"}
    for token, name in ((org_a_token, "M4 Org A"), (org_b_token, "M4 Org B")):
        client.headers["Authorization"] = f"Bearer {token}"
        applied = client.post(
            "/api/organizations/apply",
            data={"name": name, "location_consent": "false"},
            files=[("document", ("v.pdf", b"%PDF-1.4 m4", "application/pdf"))],
        )
        assert applied.status_code == 201, applied.text
        org_id = applied.json()["id"]
        assert client.post(
            f"/api/organizations/admin/{org_id}/verify", headers=admin_headers
        ).status_code == 200
        category = next(c for c in client.get("/api/categories").json() if c["code"] == "clothing")
        need = client.post(
            "/api/needs",
            json={"category_id": category["id"], "title": f"{name} clothing need",
                  "unit": "pieces", "quantity_required": 25, "urgency": "high"},
        )
        assert need.status_code == 201, need.text
    client.headers.pop("Authorization")
    org_a_id = httpx.get(
        f"{BASE}/api/organizations/me", headers={"Authorization": f"Bearer {org_a_token}"}
    ).json()["id"]

    donation = httpx.post(
        f"{BASE}/api/donations",
        headers=donor_headers,
        data={"title": "M4 jackets", "category_id": next(
            c for c in httpx.get(f"{BASE}/api/categories").json() if c["code"] == "clothing"
        )["id"], "quantity": "10", "unit": "pieces", "pickup_area": "M4 area"},
        files=[("images", ("p.jpg", jpeg_bytes((10, 120, 60)), "image/jpeg"))],
    )
    assert donation.status_code == 201, donation.text
    donation_id = donation.json()["id"]
    print("donation created:", donation.json()["reference"])

    # 1. Initiate -> highest-ranked candidate (deterministic among identical needs).
    first = httpx.post(
        f"{BASE}/api/offers/initiate/{donation_id}", headers=donor_headers
    ).json()
    assert first["offer"] is not None, first
    assert first["status"] == "offered"
    print("offer 1:", first["offer"]["organization_name"], "| score:", first["offer"]["score"])
    assert first["offer"]["factor_snapshot"]["factors"]["compatibility"]["score"] == 1.0

    # 2. Decline -> next candidate gets the offer; donation stays offered.
    # The first offer goes to whichever org wins the deterministic org-id
    # tie-break; the OTHER org must receive the next offer.
    first_org_name = first["offer"]["organization_name"]
    decline_token = org_a_token if first_org_name == "M4 Org A" else org_b_token
    declined = httpx.post(
        f"{BASE}/api/offers/{first['offer']['id']}/decline",
        headers={"Authorization": f"Bearer {decline_token}"},
        json={"reason": "M4 smoke decline"},
    )
    print("decline response:", declined.status_code, declined.text[:200])
    declined = declined.json()
    assert declined["offer"]["status"] == "declined"
    next_offer = declined["next"]["offer"]
    expected_second = "M4 Org B" if first_org_name == "M4 Org A" else "M4 Org A"
    assert next_offer is not None and next_offer["organization_name"] == expected_second
    donation_status = httpx.get(
        f"{BASE}/api/donations/{donation_id}", headers=donor_headers
    ).json()["status"]
    assert donation_status == "offered"
    print("decline -> next offer to:", next_offer["organization_name"],
          "| donation still:", donation_status)

    # 3. Decliner is never re-offered: re-initiate skips the decliner.
    #    (the second org has an active offer, so re-initiate is a no-op.)
    again = httpx.post(f"{BASE}/api/offers/initiate/{donation_id}", headers=donor_headers).json()
    assert again["offer"]["id"] == next_offer["id"]
    print("re-initiate is a no-op while an offer is active: OK")

    # 4. The second org accepts -> donation accepted.
    second_org_token = org_a_token if first_org_name == "M4 Org B" else org_b_token
    second_org_id = org_b_id_m4(second_org_token, BASE)
    accept = httpx.post(
        f"{BASE}/api/offers/{next_offer['id']}/accept",
        headers={"Authorization": f"Bearer {second_org_token}"},
    )
    assert accept.status_code == 200, accept.text
    assert accept.json()["status"] == "accepted"
    assert httpx.get(f"{BASE}/api/donations/{donation_id}", headers=donor_headers).json()["status"] == "accepted"
    print("accepted -> donation accepted")

    # 5. UPI setup (org B) -> admin approval -> donor payment info visible.
    client.headers["Authorization"] = f"Bearer {second_org_token}"
    setup = client.post("/api/payments/setup", data={"upi_id": "m4orgb@okbank"})
    assert setup.status_code == 201 and setup.json()["upi_status"] == "pending_approval"
    donor_view_before = httpx.get(
        f"{BASE}/api/donations/{donation_id}/payment-info", headers=donor_headers
    )
    assert donor_view_before.status_code == 404  # pending approval -> hidden
    approved = httpx.post(
        f"{BASE}/api/organizations/admin/{second_org_id}/upi-approve",
        headers=admin_headers,
    )
    assert approved.status_code == 200
    donor_view = httpx.get(
        f"{BASE}/api/donations/{donation_id}/payment-info", headers=donor_headers
    )
    assert donor_view.status_code == 200
    assert donor_view.json()["upi_id"] == "m4orgb@okbank"
    print("UPI approved -> donor payment info visible:", donor_view.json()["upi_id"])

    # 6. Pickup lifecycle with notifications.
    pickup = httpx.post(
        f"{BASE}/api/offers/{next_offer['id']}/pickup",
        headers={"Authorization": f"Bearer {second_org_token}"},
        json={"pickup_date": "2026-11-20",
              "pickup_window_start": "2026-11-20T10:00:00",
              "pickup_window_end": "2026-11-20T12:00:00",
              "instructions": "M4 smoke pickup"},
    )
    assert pickup.status_code == 200, pickup.text
    picked = httpx.post(
        f"{BASE}/api/offers/{next_offer['id']}/picked-up",
        headers={"Authorization": f"Bearer {second_org_token}"},
    )
    assert picked.status_code == 200
    print("pickup scheduled + picked up")

    # 7. Completion: quantity_received updates the need transactionally.
    completed = httpx.post(
        f"{BASE}/api/offers/{next_offer['id']}/complete",
        headers={"Authorization": f"Bearer {second_org_token}"},
        json={"quantity_received": 9},
    )
    assert completed.status_code == 200, completed.text
    body = completed.json()
    assert body["status"] == "accepted"  # offer stays accepted; donation completed
    need_after = body["need"]
    assert need_after["quantity_fulfilled"] == 9 and need_after["remaining_quantity"] == 16
    assert httpx.get(f"{BASE}/api/donations/{donation_id}", headers=donor_headers).json()["status"] == "completed"
    repeat = httpx.post(
        f"{BASE}/api/offers/{next_offer['id']}/complete",
        headers={"Authorization": f"Bearer {second_org_token}"}, json={"quantity_received": 9},
    )
    assert repeat.status_code == 409  # idempotent: no double-count
    print("completion: need +9 (9/25), repeat blocked (409)")

    # 8. Donor payment submission -> admin manual verification.
    payment = httpx.post(
        f"{BASE}/api/payments",
        headers=donor_headers,
        data={"donation_id": donation_id, "organization_id": second_org_id,
              "transaction_reference": f"M4REF{stamp}"},
        files=[("receipt", ("r.jpg", jpeg_bytes((40, 90, 40)), "image/jpeg"))],
    )
    assert payment.status_code == 201, payment.text
    payment_id = payment.json()["id"]
    assert payment.json()["status"] == "submitted_unverified"
    donor_reject = httpx.post(
        f"{BASE}/api/payments/admin/{payment_id}/verify", headers=donor_headers
    )
    assert donor_reject.status_code == 403  # donor cannot verify
    verified = httpx.post(
        f"{BASE}/api/payments/admin/{payment_id}/verify", headers=admin_headers
    )
    assert verified.status_code == 200 and verified.json()["status"] == "verified"
    print("payment submitted -> donor cannot self-verify -> admin verified")

    # 9. Notifications: donor received the workflow events.
    donor_notifications = httpx.get(
        f"{BASE}/api/notifications", headers=donor_headers
    ).json()
    types = [n["type"] for n in donor_notifications["items"]]
    for expected in ("offer_sent", "offer_declined", "offer_accepted",
                     "pickup_scheduled", "picked_up", "donation_completed",
                     "payment_verified"):
        assert expected in types, f"missing notification: {expected} in {types}"
    print("donor notifications:", types)

    print("\nM4 SMOKE TEST: ALL CHECKS PASSED")
    return 0


def org_b_id_m4(org_b_token: str, base: str) -> str:
    response = httpx.get(f"{base}/api/organizations/me",
                         headers={"Authorization": f"Bearer {org_b_token}"})
    return response.json()["id"]


if __name__ == "__main__":
    raise SystemExit(main())
