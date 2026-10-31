"""Prepare the SEVA-AI image dataset: validate, resize, label, split.

Reads consented images from `ml/data/raw/<source-group>/<label>/*.jpg`, writes
resized copies and `labels.csv` into `ml/data/processed/`. See
`ml/data/README.md` for the consent rules, directory layout, and CSV schema.

Guarantees:
- Labels are validated against the five fixed classes; anything else fails loudly.
- Splits are stratified by label and grouped by source (all images from one
  photo session stay in the same split) with a fixed random seed (42).
- An existing `labels.csv` is never overwritten silently (`--force` required).
- The script prints split sizes and warns when a class has fewer than
  MIN_TEST_IMAGES_PER_CLASS test images (the evaluation report must repeat it).

CLI:  python ml/src/prepare_dataset.py [--force]
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

ML_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = ML_DIR / "data" / "raw"
PROCESSED_DIR = ML_DIR / "data" / "processed"
CONSENT_CSV = RAW_DIR / "consent.csv"

LABELS: tuple[str, ...] = (
    "clothing",
    "grains_rice",
    "packaged_food",
    "utensils",
    "other",
)
SEED = 42
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_DIMENSION = 1024
TRAIN_FRAC, VAL_FRAC, TEST_FRAC = 0.70, 0.15, 0.15
MIN_TEST_IMAGES_PER_CLASS = 20  # below this, the evaluation report must say so


def read_consent() -> dict[str, dict[str, str]]:
    if not CONSENT_CSV.is_file():
        sys.exit(
            f"error: {CONSENT_CSV} is missing. Every source group needs a consent "
            "reference — see ml/data/README.md."
        )
    consent: dict[str, dict[str, str]] = {}
    with CONSENT_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            group = (row.get("source_group") or "").strip()
            ref = (row.get("consent_ref") or "").strip()
            if not group or not ref:
                sys.exit("error: consent.csv rows need source_group and consent_ref")
            consent[group] = {
                "consent_ref": ref,
                "annotator": (row.get("notes") or "unspecified").strip() or "unspecified",
            }
    return consent


def collect_images(consent: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    """Walk raw/<source-group>/<label>/* and validate everything."""
    records: list[dict[str, str]] = []
    if not RAW_DIR.is_dir():
        sys.exit(f"error: raw data directory not found: {RAW_DIR}")

    for group_dir in sorted(p for p in RAW_DIR.iterdir() if p.is_dir()):
        group = group_dir.name
        if group not in consent:
            sys.exit(
                f"error: source group '{group}' has no consent reference in consent.csv"
            )
        for label_dir in sorted(p for p in group_dir.iterdir() if p.is_dir()):
            label = label_dir.name
            if label not in LABELS:
                sys.exit(
                    f"error: '{label}' in {group_dir} is not one of the fixed classes "
                    f"{LABELS}. Fix the folder name — never relabel silently."
                )
            for image_path in sorted(label_dir.iterdir()):
                if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                records.append(
                    {
                        "raw_path": str(image_path),
                        "label": label,
                        "source": group,
                        "consent_ref": consent[group]["consent_ref"],
                        "annotator": consent[group]["annotator"],
                    }
                )
    return records


def make_splits(
    records: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """Stratified by label, grouped by source, deterministic (seed 42).

    Whole source groups are assigned to one split together so images from the
    same photo session never leak across splits. Every label that has at least
    three groups gets images in all three splits; smaller labels degrade
    gracefully and the warning in main() reports the shortfall.
    """
    rng = random.Random(SEED)

    buckets: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for record in records:
        buckets[(record["label"], record["source"])].append(record)

    per_label: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for (label, source) in sorted(buckets):
        per_label[label].append((source, len(buckets[(label, source)])))

    split_of: dict[tuple[str, str], str] = {}
    for label in sorted(per_label):
        groups = list(per_label[label])
        total = sum(size for _, size in groups)
        n_train = int(total * TRAIN_FRAC)
        n_val = int(total * VAL_FRAC)
        rng.shuffle(groups)

        assigned = 0
        n_groups = len(groups)
        for index, (source, size) in enumerate(groups):
            remaining_groups = n_groups - index
            # Reserve at least two groups for val/test whenever the label has
            # more than two groups; otherwise degrade gracefully.
            if assigned < n_train and remaining_groups > 2:
                split = "train"
            elif (assigned - n_train) < n_val and remaining_groups > 1:
                split = "val"
            else:
                split = "test"
            split_of[(label, source)] = split
            assigned += size

    splits: dict[str, list[dict[str, str]]] = {"train": [], "val": [], "test": []}
    for (label, source), items in buckets.items():
        splits[split_of[(label, source)]].extend(items)
    return splits


def resize_and_copy(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Resize the long edge to MAX_DIMENSION and copy into processed/.

    Saving a fresh JPEG strips metadata (including EXIF), mirroring the
    backend's storage behaviour for uploaded donation images.
    """
    from PIL import Image

    processed: list[dict[str, str]] = []
    for row in rows:
        raw_path = Path(row["raw_path"])
        relative = Path(row["source"]) / row["label"] / raw_path.name
        destination = PROCESSED_DIR / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(raw_path) as image:
            image = image.convert("RGB")
            image.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
            image.save(destination, "JPEG", quality=88)
        processed.append({**row, "image_path": str(relative)})
    return processed


def write_labels_csv(rows: list[dict[str, str]], force: bool) -> None:
    labels_path = PROCESSED_DIR / "labels.csv"
    if labels_path.exists() and not force:
        sys.exit(
            f"error: {labels_path} already exists. Splits are never regenerated "
            "silently — pass --force if you really intend to rebuild them."
        )
    with labels_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "image_path",
                "label",
                "source",
                "consent_ref",
                "split",
                "annotator",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "image_path": row["image_path"],
                    "label": row["label"],
                    "source": row["source"],
                    "consent_ref": row["consent_ref"],
                    "split": row["split"],
                    "annotator": row["annotator"],
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the SEVA-AI dataset")
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing labels.csv (splits are never rebuilt silently)",
    )
    args = parser.parse_args()

    consent = read_consent()
    records = collect_images(consent)
    if not records:
        sys.exit("error: no images found under ml/data/raw — nothing to prepare.")

    splits = make_splits(records)

    test_counts: dict[str, int] = {label: 0 for label in LABELS}
    rows: list[dict[str, str]] = []
    for split in ("train", "val", "test"):
        for item in splits[split]:
            rows.append({"split": split, **item})
            if split == "test":
                test_counts[item["label"]] += 1

    rows = resize_and_copy(rows)
    write_labels_csv(rows, force=args.force)

    print(f"Prepared {len(rows)} images (seed {SEED}).")
    print("Test-split images per class:")
    for label in LABELS:
        count = test_counts[label]
        print(f"  {label:14s} {count}")
    small = [label for label in LABELS if 0 < test_counts[label] < MIN_TEST_IMAGES_PER_CLASS]
    empty = [label for label in LABELS if test_counts[label] == 0]
    if small:
        print(
            f"WARNING: fewer than {MIN_TEST_IMAGES_PER_CLASS} test images for: "
            f"{', '.join(small)}. The evaluation report must state this limitation."
        )
    if empty:
        print(
            f"WARNING: no test images at all for: {', '.join(empty)}. "
            "Evaluation for those classes will be impossible."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
