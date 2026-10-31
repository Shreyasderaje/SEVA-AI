"""Stage 1 integration test: run the live /api/classify endpoint against one
HELD-OUT test image per class (never training images) and print measured
predictions.

Prerequisites: the backend must run in an environment that has torch (the ML
venv) and the trained weights at CLASSIFIER_WEIGHTS_PATH:

    cd backend && ../ml/.venv/Scripts/python.exe -m uvicorn app.main:app --port 8011
    ml/.venv/Scripts/python.exe ml/src/test_classify_api.py http://localhost:8011
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import httpx

ML_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ML_DIR / "data" / "processed"
LABELS_CSV = PROCESSED_DIR / "labels.csv"
CLASSES = ["clothing", "grains_rice", "packaged_food", "utensils", "other"]


def one_test_image_per_class() -> dict[str, Path]:
    """Pick the first held-out test image per class from labels.csv."""
    chosen: dict[str, Path] = {}
    with LABELS_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            label = row["label"]
            if row["split"] == "test" and label not in chosen:
                chosen[label] = PROCESSED_DIR / row["image_path"]
    return chosen


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8011"
    client = httpx.Client(base_url=base, timeout=60)

    email = f"classify.test.{sys.argv[2] if len(sys.argv) > 2 else 'x'}@example.com"
    reg = client.post(
        "/api/auth/register",
        json={"email": email, "password": "ClassifyPass1", "full_name": "Classify Test",
              "role": "donor"},
    )
    if reg.status_code == 409:
        reg = client.post("/api/auth/login", json={"email": email, "password": "ClassifyPass1"})
    assert reg.status_code in (200, 201), reg.text
    client.headers["Authorization"] = f"Bearer {reg.json()['access_token']}"

    # Fallback check first: oversized/garbage payload is rejected cleanly.
    bad = client.post("/api/classify", files={"image": ("x.jpg", b"not-an-image", "image/jpeg")})
    print(f"invalid image -> HTTP {bad.status_code} (expect 422)")
    assert bad.status_code == 422

    correct = 0
    total = 0
    test_images = one_test_image_per_class()
    for label in CLASSES:
        image_path = test_images.get(label)
        if image_path is None or not image_path.is_file():
            print(f"[{label}] NO TEST IMAGE FOUND — check the dataset")
            continue
        response = client.post(
            "/api/classify",
            files={"image": (image_path.name, image_path.read_bytes(), "image/jpeg")},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        if body.get("status") == "model_not_configured":
            print(f"[{label}] model_not_configured — weights not loaded by this server")
            return 3
        alternatives = ", ".join(
            f"{a['category']} {a['probability']:.2f}" for a in body.get("top_alternatives", [])
        )
        hit = "HIT " if body["predicted_category"] == label else "MISS"
        if body["predicted_category"] == label:
            correct += 1
        total += 1
        print(
            f"[{label}] {hit} predicted={body['predicted_category']} "
            f"confidence={body['confidence']:.3f} alternatives=[{alternatives}] "
            f"(test image: {image_path.name})"
        )

    print(f"\nmeasured single-image hits on held-out test images: {correct}/{total}")
    print("NOTE: one image per class is a smoke check, not an evaluation — "
          "see ml/reports/ for the full held-out test metrics.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
