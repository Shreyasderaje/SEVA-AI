"""Train the SEVA-AI image classifier (MobileNetV2 transfer learning).

Reads `ml/data/processed/labels.csv` (produced by `prepare_dataset.py`), trains
the classifier head with the backbone frozen, optionally fine-tunes the last
MobileNet blocks at a lower learning rate, and saves the best weights (by
validation accuracy) plus `model_metadata.json` next to them.

Reports produced here:
- `ml/reports/training_history.json` — per-epoch train/val loss and val accuracy
- `ml/reports/loss_curves.png` — training and validation loss curves

Honesty rules:
- Seed 42 for Python, NumPy, and PyTorch; recorded in the metadata.
- Training and validation splits are used for model selection ONLY; the TEST
  SPLIT IS NEVER TOUCHED HERE. Evaluation happens once, in
  `evaluate_image_classifier.py`.
- Nothing is claimed about accuracy unless measured by the evaluation script
  on the held-out test split.

CLI:
  ml/.venv/Scripts/python.exe ml/src/train_image_classifier.py --epochs 12
  ml/.venv/Scripts/python.exe ml/src/train_image_classifier.py --fine-tune --ft-epochs 2
  ml/.venv/Scripts/python.exe ml/src/train_image_classifier.py --register
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import random
import sys
from pathlib import Path

import numpy as np

ML_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_DIR / "src"))

PROCESSED_DIR = ML_DIR / "data" / "processed"
MODELS_DIR = ML_DIR / "models"
REPORTS_DIR = ML_DIR / "reports"

SEED = 42
CLASSES: tuple[str, ...] = (
    "clothing",
    "grains_rice",
    "packaged_food",
    "utensils",
    "other",
)
BATCH_SIZE = 32
BASE_LR = 1e-3
FINE_TUNE_LR = 1e-5
UNFREEZE_LAST_BLOCKS = 3


def set_seeds() -> None:
    random.seed(SEED)
    np.random.seed(SEED)
    import torch

    torch.manual_seed(SEED)
    if torch.cuda.is_available():  # pragma: no cover — CPU-only project
        torch.cuda.manual_seed_all(SEED)


def load_split(split: str) -> list[tuple[Path, int]]:
    labels_path = PROCESSED_DIR / "labels.csv"
    if not labels_path.is_file():
        sys.exit(
            "error: labels.csv not found — run ml/src/prepare_dataset.py first."
        )
    rows: list[tuple[Path, int]] = []
    with labels_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["split"] != split:
                continue
            label = row["label"]
            if label not in CLASSES:
                sys.exit(f"error: unexpected label '{label}' in labels.csv")
            rows.append((PROCESSED_DIR / row["image_path"], CLASSES.index(label)))
    if not rows:
        sys.exit(f"error: split '{split}' has no images.")
    return rows


class SevaDataset:
    """Minimal dataset over labels.csv rows (no augmentation — honest, simple)."""

    def __init__(self, rows: list[tuple[Path, int]]) -> None:
        from PIL import Image
        from torchvision import transforms

        self.rows = rows
        self.transform = transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
            ]
        )
        self._image = Image

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int):
        path, label = self.rows[index]
        with self._image.open(path) as image:
            tensor = self.transform(image.convert("RGB"))
        return tensor, label


def freeze_backbone(model) -> None:
    for parameter in model.features.parameters():
        parameter.requires_grad = False


def unfreeze_last_blocks(model, count: int) -> None:
    for block in list(model.features.children())[-count:]:
        for parameter in block.parameters():
            parameter.requires_grad = True


def run_epoch(model, loader, device, criterion, optimizer) -> tuple[float, float, float]:
    """One training pass; returns (avg_loss, correct, total)."""
    import torch

    model.train()
    running_loss = 0.0
    correct = total = 0
    for inputs, targets in loader:
        inputs, targets = inputs.to(device), targets.to(device)
        optimizer.zero_grad()
        outputs = model(inputs)
        loss = criterion(outputs, targets)
        loss.backward()
        optimizer.step()
        running_loss += loss.item() * targets.numel()
        correct += (outputs.argmax(dim=1) == targets).sum().item()
        total += targets.numel()
    return running_loss / max(total, 1), correct, total


def evaluate(model, loader, device) -> tuple[float, float]:
    """Validation pass with loss; returns (avg_loss, accuracy). No grad."""
    import torch
    import torch.nn as nn

    criterion = nn.CrossEntropyLoss()
    model.eval()
    running_loss = 0.0
    correct = total = 0
    with torch.no_grad():
        for inputs, targets in loader:
            inputs, targets = inputs.to(device), targets.to(device)
            outputs = model(inputs)
            running_loss += criterion(outputs, targets).item() * targets.numel()
            correct += (outputs.argmax(dim=1) == targets).sum().item()
            total += targets.numel()
    return running_loss / max(total, 1), correct / total if total else 0.0


def train_phase(model, train_loader, val_loader, device, epochs: int, lr: float, phase: str,
                history: list[dict]) -> float:
    import torch
    import torch.nn as nn

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(
        (p for p in model.parameters() if p.requires_grad), lr=lr
    )
    best_val = 0.0
    for epoch in range(1, epochs + 1):
        train_loss, correct, total = run_epoch(model, train_loader, device, criterion, optimizer)
        train_acc = correct / max(total, 1)
        val_loss, val_accuracy = evaluate(model, val_loader, device)
        best_val = max(best_val, val_accuracy)
        history.append(
            {
                "phase": phase,
                "epoch": epoch,
                "train_loss": round(train_loss, 5),
                "train_accuracy": round(train_acc, 5),
                "val_loss": round(val_loss, 5),
                "val_accuracy": round(val_accuracy, 5),
            }
        )
        print(
            f"[{phase}] epoch {epoch:3d}/{epochs}  "
            f"train_loss={train_loss:.4f} train_acc={train_acc:.4f}  "
            f"val_loss={val_loss:.4f} val_acc={val_accuracy:.4f}"
        )
    return best_val


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the SEVA-AI classifier")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--fine-tune", action="store_true")
    parser.add_argument("--ft-epochs", type=int, default=2)
    parser.add_argument("--version", type=str, default=None,
                        help="model version tag (default: auto v<N>)")
    parser.add_argument("--register", action="store_true",
                        help="also register the model in the backend model_versions table")
    args = parser.parse_args()

    try:
        import torch
        from torch.utils.data import DataLoader
        from torchvision import models
        import torch.nn as nn
    except ImportError:
        sys.exit(
            "error: PyTorch is not installed. Install the ML dependencies from "
            "ml/requirements.txt (see ml/README.md) — the backend does not need them."
        )

    set_seeds()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device: {device} | seed: {SEED}")

    train_rows = load_split("train")
    val_rows = load_split("val")
    print(
        f"train={len(train_rows)}  val={len(val_rows)}  "
        f"(test split is reserved for evaluate_image_classifier.py)"
    )

    train_loader = DataLoader(SevaDataset(train_rows), batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(SevaDataset(val_rows), batch_size=BATCH_SIZE)

    # Transfer learning: ImageNet backbone for the FEATURES, fresh 5-class head.
    # The architecture is unchanged from the M2 design (MobileNetV2, 224x224,
    # ImageNet normalization, five fixed classes).
    model = models.mobilenet_v2(weights="IMAGENET1K_V1")
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(CLASSES))
    freeze_backbone(model)
    model.to(device)

    history: list[dict] = []
    best_val = train_phase(model, train_loader, val_loader, device, args.epochs, BASE_LR,
                           "frozen-head", history)

    fine_tuned = False
    if args.fine_tune:
        unfreeze_last_blocks(model, UNFREEZE_LAST_BLOCKS)
        model.to(device)
        best_val = train_phase(model, train_loader, val_loader, device, args.ft_epochs,
                               FINE_TUNE_LR, "fine-tune", history)
        fine_tuned = True

    # Pick the version tag and save weights + metadata + training reports.
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if args.version:
        version = args.version
    else:
        existing = list(MODELS_DIR.glob("image_classifier_v*.pt"))
        version = f"v{len(existing) + 1}"
    weights_path = MODELS_DIR / f"image_classifier_{version}.pt"
    torch.save(model.state_dict(), weights_path)

    (REPORTS_DIR / "training_history.json").write_text(
        json.dumps({"seed": SEED, "history": history}, indent=2), encoding="utf-8"
    )
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axis = plt.subplots(figsize=(8, 5))
        for phase in sorted({entry["phase"] for entry in history}):
            entries = [e for e in history if e["phase"] == phase]
            epochs = list(range(1, len(entries) + 1))
            axis.plot(epochs, [e["train_loss"] for e in entries], marker="o",
                      label=f"{phase} — train loss")
            axis.plot(epochs, [e["val_loss"] for e in entries], marker="s",
                      linestyle="--", label=f"{phase} — val loss")
        axis.set_xlabel("Epoch (within phase)")
        axis.set_ylabel("Cross-entropy loss")
        axis.set_title("SEVA-AI classifier training/validation loss (seed 42)")
        axis.legend()
        fig.tight_layout()
        fig.savefig(REPORTS_DIR / "loss_curves.png", dpi=120)
        plt.close(fig)
    except Exception as exc:  # noqa: BLE001 — chart is a nicety, never fatal
        print(f"warning: loss curves skipped ({exc})")

    metadata = {
        "model_name": "seva_image_classifier",
        "version": version,
        "architecture": "mobilenet_v2_transfer_learning",
        "classes": list(CLASSES),
        "seed": SEED,
        "trained_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "dataset_stage": "stage1_public_licensed",
        "dataset_sizes": {"train": len(train_rows), "val": len(val_rows)},
        "settings": {
            "epochs_frozen": args.epochs,
            "fine_tuned": fine_tuned,
            "epochs_fine_tune": args.ft_epochs if fine_tuned else 0,
            "learning_rate_frozen": BASE_LR,
            "learning_rate_fine_tune": FINE_TUNE_LR if fine_tuned else None,
            "batch_size": BATCH_SIZE,
            "unfrozen_blocks": UNFREEZE_LAST_BLOCKS if fine_tuned else 0,
            "input_size": 224,
            "normalization": "imagenet",
        },
        "best_val_accuracy": round(best_val, 4),
        "training_history_report": "ml/reports/training_history.json",
        # Test metrics are added by evaluate_image_classifier.py and copied into
        # the model card — never invented here.
        "test_metrics": None,
    }
    metadata_path = MODELS_DIR / f"image_classifier_{version}_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"saved weights: {weights_path}")
    print(f"saved metadata: {metadata_path}")
    print("reports: training_history.json, loss_curves.png (ml/reports/)")
    print(
        "next: ml/.venv/Scripts/python.exe ml/src/evaluate_image_classifier.py --version "
        f"{version}  (runs ONCE on the held-out test split)"
    )

    if args.register:
        from registry import ensure_model_version

        ensure_model_version(
            model_name=metadata["model_name"],
            version=version,
            kind="image_classifier",
            artifact_path=str(weights_path.relative_to(ML_DIR.parent)),
            seed=SEED,
            metadata=metadata,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
