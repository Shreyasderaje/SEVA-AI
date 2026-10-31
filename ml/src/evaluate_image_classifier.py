"""Evaluate the SEVA-AI image classifier ONCE on the held-out test split.

Reports per-class precision, recall, F1, overall accuracy, and a confusion
matrix. Writes metrics JSON, a confusion-matrix PNG, and a summary markdown to
`ml/reports/`, and records the measured test metrics into the model's
`model_metadata.json` (test_metrics field).

Honesty rules:
- The test split is touched exactly once, here.
- If any class has fewer than MIN_TEST_IMAGES_PER_CLASS test images, the
  summary explicitly states the limitation.
- Numbers shown anywhere else must be copied from these reports.

CLI:  python ml/src/evaluate_image_classifier.py --version v1
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

import numpy as np

ML_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ML_DIR / "data" / "processed"
MODELS_DIR = ML_DIR / "models"
REPORTS_DIR = ML_DIR / "reports"

SEED = 42
MIN_TEST_IMAGES_PER_CLASS = 20
CLASSES: tuple[str, ...] = (
    "clothing",
    "grains_rice",
    "packaged_food",
    "utensils",
    "other",
)


def load_test_rows() -> list[tuple[Path, int]]:
    import csv

    labels_path = PROCESSED_DIR / "labels.csv"
    if not labels_path.is_file():
        sys.exit("error: labels.csv not found — run prepare_dataset.py first.")
    rows: list[tuple[Path, int]] = []
    with labels_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["split"] == "test":
                rows.append(
                    (PROCESSED_DIR / row["image_path"], CLASSES.index(row["label"]))
                )
    if not rows:
        sys.exit("error: the test split is empty — cannot evaluate.")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the SEVA-AI classifier")
    parser.add_argument("--version", type=str, required=True)
    args = parser.parse_args()

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import torch
        from sklearn.metrics import (
            accuracy_score,
            classification_report,
            confusion_matrix,
        )
    except ImportError as exc:
        sys.exit(f"error: missing ML dependency ({exc}) — see ml/requirements.txt")

    np.random.seed(SEED)
    torch.manual_seed(SEED)

    sys.path.insert(0, str(ML_DIR / "src"))
    from predict_image import CLASSES as MODEL_CLASSES, preprocess

    if tuple(MODEL_CLASSES) != CLASSES:
        sys.exit("error: class list drift between predict_image.py and evaluate script")

    weights_path = MODELS_DIR / f"image_classifier_{args.version}.pt"
    metadata_path = MODELS_DIR / f"image_classifier_{args.version}_metadata.json"
    if not weights_path.is_file():
        sys.exit(f"error: weights not found: {weights_path}")

    from PIL import Image
    from torch.utils.data import DataLoader

    sys.path.insert(0, str(ML_DIR / "src"))
    from train_image_classifier import SevaDataset

    test_rows = load_test_rows()
    loader = DataLoader(SevaDataset(test_rows), batch_size=32)

    from predict_image import load_model

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = load_model(weights_path, device=device)

    predictions: list[int] = []
    targets: list[int] = []
    with torch.no_grad():
        for inputs, labels in loader:
            outputs = model(inputs.to(device)).argmax(dim=1)
            predictions.extend(int(p) for p in outputs.cpu())
            targets.extend(int(t) for t in labels)

    report = classification_report(
        targets, predictions, target_names=list(CLASSES), output_dict=True, zero_division=0
    )
    overall_accuracy = accuracy_score(targets, predictions)
    matrix = confusion_matrix(targets, predictions, labels=list(range(len(CLASSES))))

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    per_class = {
        CLASSES[index]: {
            "precision": round(report[CLASSES[index]]["precision"], 4),
            "recall": round(report[CLASSES[index]]["recall"], 4),
            "f1_score": round(report[CLASSES[index]]["f1-score"], 4),
            "support": int(report[CLASSES[index]]["support"]),
        }
        for index in range(len(CLASSES))
    }
    small_classes = [
        CLASSES[i] for i in range(len(CLASSES)) if int(matrix[i].sum()) < MIN_TEST_IMAGES_PER_CLASS
    ]

    metrics = {
        "model_version": args.version,
        "evaluated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "split": "test",
        "test_images": len(test_rows),
        "overall_accuracy": round(float(overall_accuracy), 4),
        "per_class": per_class,
        "confusion_matrix": matrix.tolist(),
        "limitations": (
            [f"fewer than {MIN_TEST_IMAGES_PER_CLASS} test images for: {', '.join(small_classes)}"]
            if small_classes
            else []
        ),
    }
    metrics_path = REPORTS_DIR / f"image_classifier_{args.version}_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    fig, axis = plt.subplots(figsize=(6, 5))
    image = axis.imshow(matrix, cmap="Blues")
    axis.set_xticks(range(len(CLASSES)), CLASSES, rotation=45, ha="right")
    axis.set_yticks(range(len(CLASSES)), CLASSES)
    axis.set_xlabel("Predicted")
    axis.set_ylabel("Actual")
    axis.set_title(f"SEVA-AI classifier {args.version} — confusion matrix (test)")
    for i in range(len(CLASSES)):
        for j in range(len(CLASSES)):
            axis.text(j, i, str(matrix[i, j]), ha="center", va="center")
    fig.colorbar(image)
    fig.tight_layout()
    confusion_path = REPORTS_DIR / f"image_classifier_{args.version}_confusion_matrix.png"
    fig.savefig(confusion_path, dpi=120)
    plt.close(fig)

    lines = [
        f"# SEVA-AI image classifier {args.version} — evaluation summary",
        "",
        f"- Evaluated: {metrics['evaluated_at']}",
        f"- Split: held-out test ({len(test_rows)} images, touched once)",
        f"- Overall accuracy: **{metrics['overall_accuracy']:.4f}**",
        "",
        "| Class | Precision | Recall | F1 | Support |",
        "|---|---|---|---|---|",
    ]
    for class_name, values in per_class.items():
        lines.append(
            f"| {class_name} | {values['precision']:.4f} | {values['recall']:.4f} | "
            f"{values['f1_score']:.4f} | {values['support']} |"
        )
    if small_classes:
        lines += [
            "",
            f"**Limitation:** fewer than {MIN_TEST_IMAGES_PER_CLASS} test images for: "
            f"{', '.join(small_classes)}. Metrics for these classes are not reliable, "
            "and the UI must show a limitation note.",
        ]
    summary_path = REPORTS_DIR / f"image_classifier_{args.version}_summary.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Record the measured metrics into the model metadata (test_metrics field).
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["test_metrics"] = {
            "overall_accuracy": metrics["overall_accuracy"],
            "per_class": per_class,
            "report": str(metrics_path.relative_to(ML_DIR.parent)),
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"overall accuracy: {metrics['overall_accuracy']:.4f} on {len(test_rows)} test images")
    for class_name, values in per_class.items():
        print(
            f"  {class_name:14s} precision={values['precision']:.4f} "
            f"recall={values['recall']:.4f} f1={values['f1_score']:.4f} "
            f"support={values['support']}"
        )
    if small_classes:
        print(f"LIMITATION: {', '.join(small_classes)} have < {MIN_TEST_IMAGES_PER_CLASS} test images")
    print(f"reports written to {REPORTS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
