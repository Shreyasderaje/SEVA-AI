"""Stage 1 fetcher: kitchen utensils subset from Hugging Face (MIT licence).

Downloads a balanced subset of lrad3/kitchen_utensils_13k JPGs by matching the
class keyword in each filename (the dataset ships no class CSV). Run:

    ml/.venv/Scripts/python.exe ml/src/fetch_utensils.py [--per-class 260]

Output: ml/data/raw/utensils_13k/<class>/<file>.jpg + _attribution.csv
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import csv
import sys
import time
from pathlib import Path

import httpx

ML_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = ML_DIR / "data" / "raw"
OUT_DIR = RAW_DIR / "utensils_13k"
DATASET_ID = "lrad3/kitchen_utensils_13k"
RESOLVE = f"https://huggingface.co/datasets/{DATASET_ID}/resolve/main/"
SOURCE_URL = f"https://huggingface.co/datasets/{DATASET_ID}"
LICENSE = "MIT"
CLASSES = ["bowl", "fork", "glass", "knife", "mug", "pan", "plate", "spatula", "spoon", "whisk"]


def list_files(client: httpx.Client) -> list[str]:
    response = client.get(f"https://huggingface.co/api/datasets/{DATASET_ID}", timeout=30)
    response.raise_for_status()
    return [
        s["rfilename"]
        for s in response.json()["siblings"]
        if s["rfilename"].lower().endswith(".jpg")
    ]


def class_of(filename: str) -> str | None:
    lowered = filename.lower()
    matches = [c for c in CLASSES if c in lowered]
    return matches[0] if len(matches) == 1 else None  # skip ambiguous names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-class", type=int, default=260)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(follow_redirects=True, timeout=60)

    print("Listing dataset files…")
    files = list_files(client)
    by_class: dict[str, list[str]] = {}
    for path in files:
        label = class_of(path)
        if label:
            by_class.setdefault(label, []).append(path)
    for label in CLASSES:
        print(f"  {label}: {len(by_class.get(label, []))} candidates")

    selected: list[tuple[str, str]] = []
    for label in CLASSES:
        for path in sorted(by_class.get(label, []))[: args.per_class]:
            selected.append((label, path))
    print(f"Selected {len(selected)} images ({args.per_class}/class cap).")

    attribution_path = OUT_DIR / "_attribution.csv"
    rows: list[dict[str, str]] = []

    def fetch(item: tuple[str, str]) -> tuple[str, str, str, str]:
        label, path = item
        destination = OUT_DIR / label / Path(path).name
        if destination.exists() and destination.stat().st_size > 0:
            return label, path, "cached", str(destination)
        for attempt in range(3):
            try:
                response = client.get(RESOLVE + path.replace("#", "%23"))
                response.raise_for_status()
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(response.content)
                return label, path, "ok", str(destination)
            except Exception as exc:  # noqa: BLE001
                if attempt == 2:
                    return label, path, f"failed: {exc}", ""
                time.sleep(1.5 * (attempt + 1))
        return label, path, "failed", ""  # pragma: no cover

    ok = failed = 0
    with futures.ThreadPoolExecutor(max_workers=8) as pool:
        for i, (label, path, status, destination) in enumerate(pool.map(fetch, selected)):
            if status in ("ok", "cached"):
                ok += 1
                rows.append(
                    {
                        "filename": str(Path(destination).relative_to(OUT_DIR)),
                        "source_url": f"{SOURCE_URL}/blob/main/{path}",
                        "licence": LICENSE,
                        "upstream_split": path.split("/")[0],
                    }
                )
            else:
                failed += 1
            if (i + 1) % 200 == 0:
                print(f"  {i + 1}/{len(selected)} (ok={ok}, failed={failed})")

    with attribution_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["filename", "source_url", "licence", "upstream_split"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"done: ok={ok}, failed={failed} -> {OUT_DIR}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
