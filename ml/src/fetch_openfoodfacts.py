"""Stage 1 fetcher: packaged_food images from Open Food Facts.

Open Food Facts product photos are contributed under open licences (CC-BY-SA /
CC0 per upload, credited per photo). This fetcher pulls product front images
with their product URLs so every image keeps its source record. Run:

    ml/.venv/Scripts/python.exe ml/src/fetch_openfoodfacts.py [--count 1400]

Output: ml/data/raw/openfoodfacts/packaged_food/<code>.jpg + _attribution.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import httpx

ML_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = ML_DIR / "data" / "raw"
OUT_DIR = RAW_DIR / "openfoodfacts" / "packaged_food"
API = "https://world.openfoodfacts.org/api/v2/search"
USER_AGENT = "SEVA-AI-mini-project/1.0 (college dataset collection)"

FIELDS = "code,product_name,image_front_url,photographer,image_url"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1400)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=60
    )

    attribution_path = OUT_DIR.parent / "_attribution.csv"
    rows: list[dict[str, str]] = []
    page = 1
    saved = 0
    seen_codes: set[str] = set()

    while saved < args.count and page <= 40:
        try:
            response = client.get(
                API,
                params={
                    "fields": FIELDS,
                    "page_size": 100,
                    "page": page,
                    "json": "1",
                },
                timeout=60,
            )
            response.raise_for_status()
            products = response.json().get("products") or []
        except Exception as exc:  # noqa: BLE001
            print(f"page {page} failed: {exc}")
            page += 1
            time.sleep(2)
            continue

        if not products:
            break

        for product in products:
            if saved >= args.count:
                break
            code = (product.get("code") or "").strip()
            image_url = product.get("image_front_url") or product.get("image_url")
            if not code or not image_url or code in seen_codes:
                continue
            seen_codes.add(code)
            destination = OUT_DIR / f"{code}.jpg"
            try:
                if destination.exists() and destination.stat().st_size > 0:
                    pass  # already downloaded in an earlier run — keep attribution
                else:
                    image = client.get(image_url, timeout=60)
                    image.raise_for_status()
                    if len(image.content) < 4_000:  # skip placeholders
                        continue
                    destination.write_bytes(image.content)
            except Exception:  # noqa: BLE001
                continue
            saved += 1
            rows.append(
                {
                    "filename": f"packaged_food/{code}.jpg",
                    "source_url": f"https://world.openfoodfacts.org/product/{code}",
                    "licence": "CC-BY-SA / CC0 (Open Food Facts contributor)",
                    "photographer": (product.get("photographer") or "OFF contributor")[:200],
                }
            )
        print(f"page {page}: cumulative saved={saved}")
        page += 1
        time.sleep(1)  # be polite to the public API

    with attribution_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["filename", "source_url", "licence", "photographer"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"done: {saved} images -> {OUT_DIR}")
    return 0 if saved > 300 else 1


if __name__ == "__main__":
    sys.exit(main())
