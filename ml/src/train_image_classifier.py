"""Train the SEVA-AI image classifier (MobileNetV2 transfer learning).

Reads `ml/data/processed/labels.csv` (produced by `prepare_dataset.py`), trains
the classifier head with the backbone frozen, and optionally fine-tunes the
last MobileNet blocks at a lower learning rate. Saves the best weights (by
validation accuracy) plus `model_metadata.json` next to them.

Honesty rules:
- Seed 42 for Python, NumPy, and PyTorch; recorded in the metadata.
- The TEST SPLIT IS NEVER TOUCHED HERE. Evaluation happens once, in
  `evaluate_image_classifier.py`.
- Nothing is claimed about accuracy unless measured by the evaluation script
  on the held-out test split.

CLI:
  python ml/src/train_image_classifier.py --epochs 15
  python ml/src/train_image_classifier.py --epochs 15 --fine-tune --ft-epochs 5
  python ml/src/train_image_classifier.py --register   # also insert into model_versions
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
PROCESSED_DIR = ML_DIR / "data" / "processed"
MODELS_DIR = ML_DIR / "models"

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
UNFREEZE_LAST_BLOCKS = 3  # MobileNetV2 features[-N:] are unfrozen for fine-tuning


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
        from torchvision import transforms
        from PIL import Image

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


def evaluate(model, loader, device) -> float:
    import torch

    model.eval()
    correct = total = 0
    with torch.no_grad():
        for inputs, targets in loader:
            inputs, targets = inputs.to(device), targets.to(device)
            predictions = model(inputs).argmax(dim=1)
            correct += (predictions == targets).sum().item()
            total += targets.numel()
    return correct / total if total else 0.0


def train_phase(model, train_loader, val_loader, device, epochs: int, lr: float, phase: str) -> float:
    import torch
    import torch.nn as nn

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(
        (p for p in model.parameters() if p.requires_grad), lr=lr
    )
    best_val = 0.0
    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        for inputs, targets in train_loader:
            inputs, targets = inputs.to(device), targets.to(device)
            optimizer.zero_grad()
            loss = criterion(model(inputs), targets)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * targets.numel()
        val_accuracy = evaluate(model, val_loader, device)
        best_val = max(best_val, val_accuracy)
        print(
            f"[{phase}] epoch {epoch:3d}/{epochs}  "
            f"train_loss={running_loss / len(train_loader.dataset):.4f}  "
            f"val_acc={val_accuracy:.4f}"
        )
    return best_val


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the SEVA-AI classifier")
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--fine-tune", action="store_true")
    parser.add_argument("--ft-epochs", type=int, default=5)
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

    train_rows = load_split("train")
    val_rows = load_split("val")
    print(
        f"train={len(train_rows)}  val={len(val_rows)}  "
        f"(test split is reserved for evaluate_image_classifier.py)"
    )

    train_loader = DataLoader(SevaDataset(train_rows), batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(SevaDataset(val_rows), batch_size=BATCH_SIZE)

    # Transfer learning: ImageNet backbone for the FEATURES, fresh 5-class head.
    model = models.mobilenet_v2(weights="IMAGENET1K_V1")
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(CLASSES))
    freeze_backbone(model)
    model.to(device)

    best_val = train_phase(model, train_loader, val_loader, device, args.epochs, BASE_LR, "frozen-head")

    fine_tuned = False
    if args.fine_tune:
        unfreeze_last_blocks(model, UNFREEZE_LAST_BLOCKS)
        model.to(device)
        best_val = train_phase(
            model, train_loader, val_loader, device, args.ft_epochs, FINE_TUNE_LR, "fine-tune"
        )
        fine_tuned = True

    # Pick the version tag and save weights + metadata.
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if args.version:
        version = args.version
    else:
        existing = list(MODELS_DIR.glob("image_classifier_v*.pt"))
        version = f"v{len(existing) + 1}"
    weights_path = MODELS_DIR / f"image_classifier_{version}.pt"
    torch.save(model.state_dict(), weights_path)

    metadata = {
        "model_name": "seva_image_classifier",
        "version": version,
        "architecture": "mobilenet_v2_transfer_learning",
        "classes": list(CLASSES),
        "seed": SEED,
        "trained_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "dataset_sizes": {"train": len(train_rows), "val": len(val_rows)},
        "settings": {
            "epochs_frozen": args.epochs,
            "fine_tuned": fine_tuned,
            "epochs_fine_tune": args.ft_epochs if fine_tuned else 0,
            "learning_rate_frozen": BASE_LR,
            "learning_rate_fine_tune": FINE_TUNE_LR if fine_tuned else None,
            "batch_size": BATCH_SIZE,
            "unfrozen_blocks": UNFREEZE_LAST_BLOCKS if fine_tuned else 0,
        },
        "best_val_accuracy": round(best_val, 4),
        # Test metrics are added by evaluate_image_classifier.py and copied into
        # the model card — never invented here.
        "test_metrics": None,
    }
    metadata_path = MODELS_DIR / f"image_classifier_{version}_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"saved weights: {weights_path}")
    print(f"saved metadata: {metadata_path}")
    print(
        "next: python ml/src/evaluate_image_classifier.py --version "
        f"{version}  (runs ONCE on the held-out test split)"
    )

    if args.register:
        register_in_backend(weights_path, metadata_path, metadata)

    return 0


def register_in_backend(weights_path: Path, metadata_path: Path, metadata: dict) -> None:
    """Optional: insert the model version into the backend's model_versions table."""
    backend_dir = ML_DIR.parent / "backend"
    sys.path.insert(0, str(backend_dir))
    try:
        from app.core.database import SessionLocal
        from app.models.ml import ModelVersion
    except ImportError as exc:  # pragma: no cover
        print(f"warning: could not import the backend app ({exc}); not registered.")
        return

    session = SessionLocal()
    try:
        row = ModelVersion(
            model_name=metadata["model_name"],
            version=metadata["version"],
            kind="image_classifier",
            artifact_path=str(weights_path.relative_to(ML_DIR.parent)),
            seed=SEED,
            metadata_json=json.dumps(metadata),
            is_active=True,
        )
        session.add(row)
        session.commit()
        print(f"registered in model_versions (id={row.id})")
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
