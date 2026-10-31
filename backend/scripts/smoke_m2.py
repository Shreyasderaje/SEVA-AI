"""M2 full-stack smoke test (run against the live dev servers).

Run:  backend/.venv/Scripts/python.exe scripts/smoke_m2.py [base_url]
Default base_url is http://localhost:8010 (backend directly).
"""

import io
import sys
import time

import httpx
from PIL import Image

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8010"


def jpeg_bytes(color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=color).save(buf, "JPEG")
    return buf.getvalue()


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=30)
    # Unique per run so the script can be run repeatedly against a live server.
    email = f"smoke.m2.{int(time.time())}@example.com"

    # 1. Health
    health = client.get("/api/health")
    print("health:", health.status_code, health.json()["database"])
    assert health.status_code == 200

    # 2. Register/login donor
    reg = client.post(
        "/api/auth/register",
        json={"email": email, "password": "SmokeM2Pass1", "full_name": "Smoke M2", "role": "donor"},
    )
    if reg.status_code == 409:
        reg = client.post("/api/auth/login", json={"email": email, "password": "SmokeM2Pass1"})
    assert reg.status_code in (200, 201), reg.text
    token = reg.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    print("auth:", reg.status_code, "role:", reg.json()["user"]["role"])

    # 3. Categories
    categories = client.get("/api/categories").json()
    clothing = next(c for c in categories if c["code"] == "clothing")
    print("categories:", [c["code"] for c in categories],
          "| clothing subcats:", [s["display_name"] for s in clothing["subcategories"]])

    # 4. Classify (honest fallback)
    classify = client.post(
        "/api/classify",
        files={"image": ("primary.jpg", jpeg_bytes((200, 120, 40)), "image/jpeg")},
    )
    print("classify:", classify.status_code, classify.json())
    assert classify.json() == {"status": "model_not_configured"}

    # 5. Create donation with 2 images (primary + supporting), PNG primary
    png_buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=(10, 60, 200)).save(png_buf, "PNG")
    create = client.post(
        "/api/donations",
        data={
            "title": "Warm blankets and jackets",
            "description": "Gently used winter items",
            "category_id": clothing["id"],
            "subcategory_id": clothing["subcategories"][0]["id"],
            "quantity": "8",
            "unit": "pieces",
            "condition": "good",
            "pickup_area": "Near Central Library",
            "pickup_latitude": "12.9716",
            "pickup_longitude": "77.5946",
            "location_consent": "true",
        },
        files=[
            ("images", ("primary.png", png_buf.getvalue(), "image/png")),
            ("images", ("second.jpg", jpeg_bytes((90, 90, 90)), "image/jpeg")),
        ],
    )
    print("create:", create.status_code)
    assert create.status_code == 201, create.text
    donation = create.json()
    print("  reference:", donation["reference"], "| status:", donation["status"])
    print("  category:", donation["category_code"], "+", donation["subcategory_display_name"])
    print("  ai fields:", donation["ai_predicted_category"], donation["ai_confidence"])
    print("  images:", [(i["position"], i["mime_type"], i["size_bytes"]) for i in donation["images"]])
    print("  timeline:", [(t["from_status"], t["to_status"]) for t in donation["timeline"]])
    print("  coords stored with consent:", donation["location_consent"], donation["pickup_latitude"])
    assert donation["status"] == "pending"
    assert [i["position"] for i in donation["images"]] == [1, 2]
    assert donation["images"][0]["mime_type"] == "image/jpeg"  # PNG re-encoded

    # 6. Fetch the stored primary image (authorized)
    image = client.get(donation["images"][0]["url"])
    print("image fetch:", image.status_code, image.headers.get("content-type"),
          "magic:", image.content[:3])
    assert image.status_code == 200 and image.content[:3] == b"\xff\xd8\xff"

    # 7. List + filters
    listing = client.get("/api/donations", params={"q": "blankets"})
    print("list q=blankets:", listing.json()["total"])
    assert listing.json()["total"] == 1

    # 8. Summary + cancel
    summary = client.get("/api/donations/summary").json()
    print("summary:", summary)
    cancelled = client.post(f"/api/donations/{donation['id']}/cancel")
    print("cancel:", cancelled.status_code, cancelled.json()["status"],
          "| timeline:", [(t["from_status"], t["to_status"]) for t in cancelled.json()["timeline"]])
    assert cancelled.json()["status"] == "cancelled"
    double = client.post(f"/api/donations/{donation['id']}/cancel")
    print("double cancel:", double.status_code, double.json()["detail"])
    assert double.status_code == 409

    # 9. IDOR: another donor cannot see it
    other = client.post(
        "/api/auth/register",
        json={"email": "smoke.m2.other@example.com", "password": "SmokeM2Pass1",
              "full_name": "Other Donor", "role": "donor"},
    )
    if other.status_code == 409:  # already registered by an earlier smoke run
        other = client.post(
            "/api/auth/login",
            json={"email": "smoke.m2.other@example.com", "password": "SmokeM2Pass1"},
        )
    other_token = other.json()["access_token"]
    forbidden = client.get(
        f"/api/donations/{donation['id']}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    print("IDOR check:", forbidden.status_code)
    assert forbidden.status_code == 404

    print("\nM2 SMOKE TEST: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
