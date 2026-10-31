"""Stage 1 fetcher: "other" class images from Wikimedia Commons.

Fetches images of miscellaneous household donation items (books, toys, board
games, stuffed toys) from Wikimedia Commons categories, keeping ONLY files
whose licence metadata is CC0 / Public Domain / CC BY / CC BY-SA (any version).
Per-image attribution (artist, licence, source URL) is captured from the
Commons API and stored in _attribution.csv — licence verification happens per
actual file, not per repository.

Run:  ml/.venv/Scripts/python.exe ml/src/fetch_wikimedia_other.py [--per-category 260]

Output: ml/data/raw/wikimedia_other/<class>/<file>.jpg + _attribution.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from pathlib import Path

import httpx

ML_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = ML_DIR / "data" / "raw"
OUT_DIR = RAW_DIR / "wikimedia_other"
API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = (
    "SEVA-AI-mini-project/1.0 (https://github.com/seva-ai/seva-ai; "
    "seva-ai@example.com) college dataset collection"
)

# Commons categories → SEVA "other" class (verified to contain direct files)
CATEGORIES = {
    "toys": "Category:Toys",
    "dolls": "Category:Dolls",
    "stuffed_toys": "Category:Plush toys",
    "books": "Category:Books",
    "board_games": "Category:Board games",
    "childrens_games": "Category:Children's games",
    "school_supplies": "Category:School supplies",
}

ALLOWED_LICENCE = re.compile(
    r"(cc0|public domain|cc by(?!-nc)|cc-by(?!-nc)|attribution)", re.IGNORECASE
)
FORBIDDEN_LICENCE = re.compile(r"(nc|nd|non-free|fair use)", re.IGNORECASE)
IMAGE_EXTS = (".jpg", ".jpeg", ".png")
MIN_BYTES = 8_000  # skip icons/thumbnails
MAX_BYTES = 12_000_000


def file_prefix(title: str) -> str:
    return title.replace(" ", "_")


def api_get(client: httpx.Client, **params) -> dict:
    params["format"] = "json"
    for attempt in range(3):
        try:
            response = client.get(API, params=params, timeout=40)
            response.raise_for_status()
            return response.json()
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")  # pragma: no cover


def fetch_category(client: httpx.Client, category: str, limit: int) -> list[dict]:
    """List image files in a category with licence metadata, filtered to
    permissive licences. Returns records ready for download."""
    records: list[dict] = []
    continuation: dict | None = None
    while len(records) < limit:
        params: dict = {
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": category,
            "gcmtype": "file",
            "gcmlimit": 100,
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": 1024,
        }
        if continuation:
            params.update(continuation)
        data = api_get(client, **params)
        pages = (data.get("query") or {}).get("pages") or {}
        for page in pages.values():
            title = page.get("title", "")
            if not title.lower().endswith(IMAGE_EXTS):
                continue
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            info = infos[0]
            metadata = info.get("extmetadata") or {}

            def field(name: str) -> str:
                value = (metadata.get(name) or {}).get("value") or ""
                # strip HTML tags from extmetadata values
                return re.sub(r"<[^>]+>", "", str(value)).strip()

            licence = field("LicenseShortName") or field("UsageTerms")
            if not licence or FORBIDDEN_LICENCE.search(licence):
                continue
            if not ALLOWED_LICENCE.search(licence):
                continue
            url = info.get("thumburl") or info.get("url")
            size = info.get("size") or 0
            if not url or size < MIN_BYTES:
                continue
            records.append(
                {
                    "title": title,
                    "url": url,
                    "size": size,
                    "licence": licence,
                    "artist": field("Artist") or "Unknown",
                    "description_url": info.get("descriptionurl") or "",
                }
            )
            if len(records) >= limit:
                break
        continuation = data.get("continue")
        if not continuation:
            break
    return records[:limit]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-category", type=int, default=260)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=60)

    attribution_rows: list[dict[str, str]] = []
    total_ok = 0
    for label, category in CATEGORIES.items():
        print(f"[{label}] fetching from {category} (cap {args.per_category})…")
        try:
            records = fetch_category(client, category, args.per_category)
        except Exception as exc:  # noqa: BLE001
            print(f"  category fetch failed: {exc}")
            continue
        ok = 0
        # All Wikimedia categories map into the single SEVA "other" class;
        # the category is kept as a filename prefix for traceability.
        (OUT_DIR / "other").mkdir(parents=True, exist_ok=True)
        for record in records:
            filename = re.sub(r"[^A-Za-z0-9._-]", "_", file_prefix(record["title"]))[-120:]
            filename = f"{label}__{filename}"
            destination = OUT_DIR / "other" / filename
            try:
                response = client.get(record["url"], timeout=60)
                response.raise_for_status()
                if len(response.content) > MAX_BYTES:
                    continue
                destination.write_bytes(response.content)
            except Exception:  # noqa: BLE001
                continue
            attribution_rows.append(
                {
                    "filename": f"other/{filename}",
                    "source_url": record["description_url"],
                    "licence": record["licence"],
                    "artist": record["artist"][:200],
                }
            )
            ok += 1
        total_ok += ok
        print(f"  saved {ok} images")

    attribution_path = OUT_DIR / "_attribution.csv"
    with attribution_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["filename", "source_url", "licence", "artist"]
        )
        writer.writeheader()
        writer.writerows(attribution_rows)

    print(f"done: {total_ok} images -> {OUT_DIR}")
    return 0 if total_ok > 100 else 1


if __name__ == "__main__":
    sys.exit(main())
