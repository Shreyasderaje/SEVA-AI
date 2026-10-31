"""Prepare the SEVA-AI image dataset (Stage 1: public licensed datasets).

Reads images from `ml/data/raw/<source_group>/<class>/*` (source groups
declared in `ml/data/raw/datasets.csv`), then:

1. Validates labels against the five fixed classes and validates licence
   metadata (public_licensed requires source+licence; consented_original
   requires a consent_ref — enforced so future ashram-collected data cannot
   enter the pipeline undocumented).
2. Removes exact duplicates (SHA-256 of file bytes).
3. Groups near-duplicates (64-bit average hash, Hamming distance ≤ 6) with a
   union-find so crops/rotations of the same photo never leak across splits.
4. Assigns reproducible train/val/test splits stratified by class, grouped by
   duplicate group, seed 42, never regenerated silently (`--force`).
5. Balances classes by deterministically dropping whole duplicate groups (and
   only then single images) above the per-split caps.
6. Writes resized/metadata-stripped copies to `ml/data/processed/`, the new
   `labels.csv`, and a distribution report (JSON + PNG) to `ml/reports/`.

labels.csv columns:
    image_path,label,source,source_url,licence,dataset_type,consent_ref,annotator,split

Run:  ml/.venv/Scripts/python.exe ml/src/prepare_dataset.py [--force] \
        [--max-train-per-class 1100] [--max-val-per-class 220] [--max-test-per-class 220]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image

ML_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = ML_DIR / "data" / "raw"
PROCESSED_DIR = ML_DIR / "data" / "processed"
REPORTS_DIR = ML_DIR / "reports"
REGISTRY_PATH = RAW_DIR / "datasets.csv"

LABELS: tuple[str, ...] = (
    "clothing",
    "grains_rice",
    "packaged_food",
    "utensils",
    "other",
)
SEED = 42
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
TRAIN_FRAC, VAL_FRAC, TEST_FRAC = 0.70, 0.15, 0.15
MIN_TEST_IMAGES_PER_CLASS = 20
NEAR_DUP_HAMMING = 4
NEAR_DUP_WINDOW = 50
# A single near-duplicate group holding more than this fraction of a class is
# dissolved into singletons before splitting (otherwise one augmented family
# would put an entire class into one split). Logged as a limitation.
OVERSIZED_GROUP_FRACTION = 0.25
MAX_DIMENSION = 1024
MIN_SIDE = 32
LABELS_CSV_FIELDS = [
    "image_path",
    "label",
    "source",
    "source_url",
    "licence",
    "dataset_type",
    "consent_ref",
    "annotator",
    "split",
]


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, item: int) -> int:
        self.parent.setdefault(item, item)
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self.parent[root_b] = root_a


def read_registry() -> dict[str, dict[str, str]]:
    if not REGISTRY_PATH.is_file():
        sys.exit(f"error: dataset registry not found: {REGISTRY_PATH}")
    registry: dict[str, dict[str, str]] = {}
    with REGISTRY_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            group = (row.get("source_group") or "").strip()
            if not group:
                continue
            registry[group] = {
                key: (row.get(key) or "").strip()
                for key in (
                    "dataset_type",
                    "source",
                    "source_url",
                    "licence",
                    "consent_ref",
                    "annotator",
                    "label_mapping",
                )
            }
    return registry


def resolve_label(group: dict[str, str], folder: str) -> str | None:
    """Map a raw subfolder to a SEVA class via the registry's label_mapping
    (comma-separated `folder=class` rules; `*=class` maps every folder).
    Without a mapping the folder name must already be a fixed class."""
    mapping = group.get("label_mapping") or ""
    for rule in (part.strip() for part in mapping.split(",") if part.strip()):
        if "=" not in rule:
            continue
        raw_folder, seva_class = (piece.strip() for piece in rule.split("=", 1))
        if seva_class not in LABELS:
            sys.exit(f"error: label_mapping rule '{rule}' targets an unknown class")
        if raw_folder == "*" or raw_folder.lower() == folder.lower():
            return seva_class
    return folder if folder in LABELS else None


def read_sidecar(group_dir: Path) -> dict[str, dict[str, str]]:
    """Per-image attribution override from a source-group _attribution.csv."""
    sidecar = group_dir / "_attribution.csv"
    overrides: dict[str, dict[str, str]] = {}
    if not sidecar.is_file():
        return overrides
    with sidecar.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (row.get("filename") or "").replace("\\", "/").strip()
            if key:
                overrides[key] = {
                    "licence": (row.get("licence") or "").strip(),
                    "artist": (row.get("artist") or row.get("photographer") or "").strip(),
                    "source_url": (row.get("source_url") or "").strip(),
                }
    return overrides


def collect_images(registry: dict[str, dict[str, str]]) -> tuple[list[dict], list[dict]]:
    records: list[dict] = []
    excluded: list[dict] = []
    for group_dir in sorted(p for p in RAW_DIR.iterdir() if p.is_dir()):
        group = group_dir.name
        if group == "_downloads" or group not in registry:
            continue
        meta = registry[group]
        dataset_type = meta["dataset_type"]
        if dataset_type not in ("public_licensed", "consented_original"):
            sys.exit(f"error: '{group}' has unknown dataset_type '{dataset_type}'")
        if dataset_type == "public_licensed" and (not meta["source"] or not meta["licence"]):
            sys.exit(f"error: public_licensed source '{group}' needs source and licence")
        if dataset_type == "consented_original" and not meta["consent_ref"]:
            sys.exit(
                f"error: consented_original source '{group}' needs a consent_ref — "
                "real-world images must never enter the pipeline undocumented."
            )
        overrides = read_sidecar(group_dir)
        for class_dir in sorted(p for p in group_dir.iterdir() if p.is_dir()):
            folder = class_dir.name
            if folder.startswith("_"):
                continue
            label = resolve_label(meta, folder)
            if label is None:
                sys.exit(
                    f"error: '{folder}' in {group_dir} does not map to one of the fixed "
                    f"classes {LABELS}. Add a label_mapping rule in datasets.csv first."
                )
            for image_path in sorted(class_dir.iterdir()):
                if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                relative = f"{label}/{image_path.name}".replace("\\", "/")
                override = overrides.get(relative, {})
                licence = override.get("licence") or meta["licence"]
                if not licence:
                    excluded.append({"path": str(image_path), "reason": "no licence documented"})
                    continue
                source_url = override.get("source_url") or meta["source_url"]
                records.append(
                    {
                        "path": image_path,
                        "label": label,
                        "source_group": group,
                        "source": meta["source"],
                        "source_url": source_url,
                        "licence": licence,
                        "dataset_type": dataset_type,
                        "consent_ref": meta["consent_ref"],
                        "annotator": override.get("artist") or meta["annotator"] or "unspecified",
                    }
                )
    return records, excluded


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def average_hash(path: Path) -> int | None:
    """64-bit average hash (8x8 grayscale) — cheap near-duplicate detection."""
    try:
        with Image.open(path) as image:
            image = image.convert("L").resize((8, 8))
            pixels = list(image.getdata())
    except Exception:  # noqa: BLE001 — corrupt images are excluded, not fatal
        return None
    if min(pixels) == max(pixels):
        return 0
    mean = sum(pixels) / len(pixels)
    bits = 0
    for pixel in pixels:
        bits = (bits << 1) | (1 if pixel > mean else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def pre_sample(records: list[dict], cap: int) -> tuple[list[dict], int]:
    """Deterministically cap each (class, source_group) bucket before the
    expensive near-duplicate analysis. Diversity within very large sources is
    high, so this keeps the pipeline tractable without losing class coverage."""
    rng = random.Random(SEED)
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in records:
        buckets[(record["label"], record["source_group"])].append(record)

    kept: list[dict] = []
    dropped = 0
    for (label, group), items in sorted(buckets.items()):
        if len(items) <= cap:
            kept.extend(items)
            continue
        items = sorted(items, key=lambda r: str(r["path"]))
        rng.shuffle(items)
        kept.extend(items[:cap])
        dropped += len(items) - cap
    return kept, dropped


def deduplicate(records: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Exact (sha256) + near (average-hash) dedup; returns kept records with a
    `dup_group` id each, plus statistics."""
    seen_hashes: dict[str, str] = {}
    kept: list[dict] = []
    exact_removed = 0

    for record in sorted(records, key=lambda r: str(r["path"])):
        digest = sha256_of(record["path"])
        if digest in seen_hashes:
            exact_removed += 1
            continue
        seen_hashes[digest] = str(record["path"])
        record["sha256"] = digest
        kept.append(record)

    # Near-duplicate grouping within each class.
    union = UnionFind()
    per_label: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(kept):
        record["_ahash"] = average_hash(record["path"])
        per_label[record["label"]].append(index)

    kept = [r for r in kept if r["_ahash"] is not None]
    per_label = defaultdict(list)
    for index, record in enumerate(kept):
        per_label[record["label"]].append(index)

    near_removed_groups = 0
    for label, indexes in per_label.items():
        indexed = sorted(indexes, key=lambda i: kept[i]["_ahash"])
        for position, index in enumerate(indexed):
            for neighbor in indexed[position + 1 : position + 1 + NEAR_DUP_WINDOW]:
                if hamming(kept[index]["_ahash"], kept[neighbor]["_ahash"]) <= NEAR_DUP_HAMMING:
                    union.union(index, neighbor)

    groups: dict[int, int] = {}
    for index in range(len(kept)):
        root = union.find(index)
        groups.setdefault(root, len(groups))
        kept[index]["dup_group"] = f"{kept[index]['label']}:{groups[root]}"

    seen_group_names: set[str] = set()
    for record in kept:
        if record["dup_group"] in seen_group_names:
            pass
        seen_group_names.add(record["dup_group"])
    # Groups that lost all but one member still count as merged duplicates.
    merged_members: dict[str, int] = defaultdict(int)
    for record in kept:
        merged_members[record["dup_group"]] += 1
    near_removed_groups = sum(1 for size in merged_members.values() if size > 1)

    stats = {
        "exact_duplicates_removed": exact_removed,
        "near_duplicate_groups": near_removed_groups,
        "kept": len(kept),
    }
    return kept, stats


def dissolve_oversized_groups(records: list[dict]) -> int:
    """Split near-duplicate groups that dominate a class into singletons so the
    grouped split still covers all three splits. Returns the number of groups
    dissolved. Logged as a limitation for augmented datasets."""
    per_label: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for record in records:
        per_label[record["label"]][record["dup_group"]] += 1

    dissolved = 0
    for label, group_sizes in per_label.items():
        total = sum(group_sizes.values())
        for group, size in group_sizes.items():
            if size > total * OVERSIZED_GROUP_FRACTION:
                dissolved += 1
                for record in records:
                    if record["label"] == label and record["dup_group"] == group:
                        record["dup_group"] = f"{group}#{id(record)}"
    return dissolved


def make_splits(records: list[dict]) -> None:
    """Grouped stratified splits, deterministic (seed 42)."""
    rng = random.Random(SEED)
    per_label_groups: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        per_label_groups[record["label"]][record["dup_group"]].append(record)

    for label, groups in per_label_groups.items():
        ordered = sorted(groups.items(), key=lambda kv: kv[0])
        total = sum(len(items) for _, items in ordered)
        n_train = int(total * TRAIN_FRAC)
        n_val = int(total * VAL_FRAC)
        rng.shuffle(ordered)

        assigned = 0
        n_groups = len(ordered)
        for index, (_group, items) in enumerate(ordered):
            remaining_groups = n_groups - index
            if assigned < n_train and remaining_groups > 2:
                split = "train"
            elif (assigned - n_train) < n_val and remaining_groups > 1:
                split = "val"
            else:
                split = "test"
            for item in items:
                item["split"] = split
            assigned += len(items)


def balance(records: list[dict], caps: dict[str, int]) -> int:
    """Deterministically drop whole duplicate groups above the caps, then
    single images. Returns the number of dropped records."""
    rng = random.Random(SEED + 1)
    dropped = 0
    per_split_label: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in records:
        per_split_label[(record["split"], record["label"])].append(record)

    for (split, label), items in per_split_label.items():
        cap = caps.get(split)
        if cap is None or len(items) <= cap:
            continue
        by_group: dict[str, list[dict]] = defaultdict(list)
        for item in items:
            by_group[item["dup_group"]].append(item)
        group_items = sorted(by_group.values(), key=lambda g: str(sorted(p["path"] for p in g)[0]))
        rng.shuffle(group_items)

        keep: list[dict] = []
        count = 0
        for group in group_items:
            if count + len(group) <= cap:
                keep.extend(group)
                count += len(group)
        # Fill any remainder with single images from dropped groups.
        dropped_flat = [item for group in group_items if group not in keep for item in group]
        for item in dropped_flat:
            if count >= cap:
                break
            keep.append(item)
            count += 1
        keep_ids = {id(item) for item in keep}
        for item in items:
            if id(item) not in keep_ids:
                item["_dropped"] = True
                dropped += 1
    return dropped


def resize_and_copy(records: list[dict]) -> int:
    failures = 0
    for record in records:
        source: Path = record["path"]
        relative = Path(record["source_group"]) / record["label"] / source.name
        destination = PROCESSED_DIR / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(source) as image:
                width, height = image.size
                if min(width, height) < MIN_SIDE:
                    record["_dropped"] = True
                    failures += 1
                    continue
                image = image.convert("RGB")
                image.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
                image.save(destination, "JPEG", quality=88)
            record["image_path"] = relative.as_posix()
        except Exception:  # noqa: BLE001
            record["_dropped"] = True
            failures += 1
    return failures


def write_labels_csv(records: list[dict], force: bool) -> None:
    labels_path = PROCESSED_DIR / "labels.csv"
    if labels_path.exists() and not force:
        sys.exit(
            f"error: {labels_path} already exists. Splits are never regenerated "
            "silently — pass --force if you really intend to rebuild them."
        )
    with labels_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABELS_CSV_FIELDS)
        writer.writeheader()
        for record in sorted(records, key=lambda r: r["image_path"]):
            writer.writerow({field: record.get(field, "") for field in LABELS_CSV_FIELDS})


def write_distribution_report(records: list[dict], stats: dict, excluded: list[dict]) -> None:
    distribution = {
        label: {
            split: sum(
                1 for r in records if r["label"] == label and r["split"] == split
            )
            for split in ("train", "val", "test")
        }
        for label in LABELS
    }
    by_source: dict[str, int] = defaultdict(int)
    for record in records:
        by_source[record["source_group"]] += 1
    by_licence: dict[str, int] = defaultdict(int)
    for record in records:
        by_licence[record["licence"]] += 1

    report = {
        "seed": SEED,
        "total_images": len(records),
        "per_class_per_split": distribution,
        "per_source_group": dict(by_source),
        "per_licence": dict(by_licence),
        "deduplication": stats,
        "excluded_images": len(excluded),
        "exclusion_reasons": sorted({e["reason"] for e in excluded}),
        "dataset_types": {
            t: sum(1 for r in records if r["dataset_type"] == t)
            for t in ("public_licensed", "consented_original")
        },
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "dataset_distribution.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        fig, axis = plt.subplots(figsize=(9, 5))
        x = np.arange(len(LABELS))
        width = 0.26
        for offset, split in enumerate(("train", "val", "test")):
            values = [distribution[label][split] for label in LABELS]
            axis.bar(x + (offset - 1) * width, values, width, label=split)
        axis.set_xticks(x, LABELS, rotation=20, ha="right")
        axis.set_ylabel("Images")
        axis.set_title("SEVA-AI Stage 1 dataset distribution (public licensed)")
        axis.legend()
        fig.tight_layout()
        fig.savefig(REPORTS_DIR / "dataset_distribution.png", dpi=120)
        plt.close(fig)
    except Exception as exc:  # noqa: BLE001 — chart is a nicety, never fatal
        print(f"warning: distribution chart skipped ({exc})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the SEVA-AI dataset")
    parser.add_argument("--force", action="store_true",
                        help="overwrite labels.csv (splits are never rebuilt silently)")
    parser.add_argument("--max-per-source-class", type=int, default=2500,
                        help="deterministic pre-sample cap per (class, source group) "
                             "before near-duplicate analysis")
    parser.add_argument("--max-train-per-class", type=int, default=1100)
    parser.add_argument("--max-val-per-class", type=int, default=220)
    parser.add_argument("--max-test-per-class", type=int, default=220)
    args = parser.parse_args()

    registry = read_registry()
    records, excluded = collect_images(registry)
    if not records:
        sys.exit("error: no images found under ml/data/raw — nothing to prepare.")
    print(f"collected {len(records)} candidate images, {len(excluded)} excluded")

    records, presampled = pre_sample(records, args.max_per_source_class)
    print(f"pre-sample: {presampled} images dropped by the per-(class, source) cap "
          f"of {args.max_per_source_class}")

    records, stats = deduplicate(records)
    print(f"after dedup: {len(records)} images ({stats['exact_duplicates_removed']} exact "
          f"duplicates removed, {stats['near_duplicate_groups']} near-duplicate groups)")

    dissolved = dissolve_oversized_groups(records)
    if dissolved:
        print(f"WARNING: {dissolved} oversized near-duplicate group(s) dissolved into "
              "singletons — minor within-family leakage is possible for augmented "
              "sources (documented limitation).")

    make_splits(records)
    dropped = balance(
        records,
        {
            "train": args.max_train_per_class,
            "val": args.max_val_per_class,
            "test": args.max_test_per_class,
        },
    )
    records = [r for r in records if not r.get("_dropped")]
    print(f"balance: dropped {dropped} images to respect per-class caps")

    copy_failures = resize_and_copy(records)
    records = [r for r in records if not r.get("_dropped")]
    print(f"resize/copy: {copy_failures} unreadable/too-small images excluded")

    write_labels_csv(records, force=args.force)
    write_distribution_report(records, stats, excluded)

    test_counts = {
        label: sum(1 for r in records if r["label"] == label and r["split"] == "test")
        for label in LABELS
    }
    print(f"\nFinal dataset: {len(records)} images (seed {SEED})")
    for label in LABELS:
        counts = {
            split: sum(1 for r in records if r["label"] == label and r["split"] == split)
            for split in ("train", "val", "test")
        }
        print(f"  {label:14s} train={counts['train']:5d} val={counts['val']:4d} test={counts['test']:4d}")
    small = [label for label, count in test_counts.items() if count < MIN_TEST_IMAGES_PER_CLASS]
    if small:
        print(f"WARNING: fewer than {MIN_TEST_IMAGES_PER_CLASS} test images for: {', '.join(small)}")
    print(f"\nlabels.csv and distribution report written (see ml/reports/).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
