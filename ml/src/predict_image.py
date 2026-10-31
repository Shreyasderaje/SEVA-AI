"""Canonical SEVA-AI image-classifier inference.

This module is the single source of truth for classifier inference logic. The
FastAPI backend wraps it through `backend/app/ml/classifier.py` (imported
lazily so the backend can run without PyTorch installed); the CLI below uses
the same functions.

Honesty rules:
- Five fixed output classes, never extended by admin display subcategories.
- Missing weights file  -> ModelNotConfiguredError (never a fabricated guess).
- PyTorch not installed -> ModelNotConfiguredError in the backend wrapper.
- ImageNet-pretrained weights are NOT a trained SEVA-AI classifier; only a
  weights file produced by `train_image_classifier.py` on a real consented
  dataset counts as the SEVA-AI model.

CLI:  python ml/src/predict_image.py path/to/image.jpg [--weights PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# The five FIXED classifier output classes (addendum §3). Admin-managed display
# subcategories never appear here.
CLASSES: tuple[str, ...] = (
    "clothing",
    "grains_rice",
    "packaged_food",
    "utensils",
    "other",
)

# ImageNet normalization used by MobileNetV2 in torchvision.
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
INPUT_SIZE = 224
TOP_ALTERNATIVES = 3


class ModelNotConfiguredError(RuntimeError):
    """Raised when the classifier cannot run (missing weights or runtime)."""


def build_model(num_classes: int = len(CLASSES)):
    """MobileNetV2 with the ImageNet classifier head replaced for SEVA-AI.

    Downloads ImageNet backbone weights at TRAINING time only; inference on an
    already-trained SEVA-AI weights file never touches the network.
    """
    import torch.nn as nn  # noqa: PLC0415 — lazy import keeps the backend torch-free
    from torchvision import models  # noqa: PLC0415

    model = models.mobilenet_v2(weights=None)
    # Replace the classifier head: keep the Dropout, swap the Linear for 5 classes.
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, num_classes)
    return model


def load_model(weights_path: str | Path, device: str = "cpu"):
    """Load trained SEVA-AI weights into the model (strict)."""
    import torch  # noqa: PLC0415

    path = Path(weights_path)
    if not path.is_file():
        raise ModelNotConfiguredError(f"Classifier weights not found at {path}")
    model = build_model()
    state_dict = torch.load(path, map_location=device, weights_only=True)
    model.load_state_dict(state_dict, strict=True)
    model.eval()
    return model.to(device)


def preprocess(image):
    """PIL.Image -> normalized input tensor (224x224, ImageNet stats)."""
    from PIL import Image  # noqa: PLC0415
    from torchvision import transforms  # noqa: PLC0415

    if not isinstance(image, Image.Image):
        raise TypeError("preprocess expects a PIL.Image")
    transform = transforms.Compose(
        [
            transforms.Resize((INPUT_SIZE, INPUT_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )
    return transform(image.convert("RGB")).unsqueeze(0)  # 1xCxHxW batch


def predict_bytes(
    image_bytes: bytes,
    weights_path: str | Path,
    device: str = "cpu",
    top_alternatives: int = TOP_ALTERNATIVES,
) -> dict:
    """Run inference on image bytes. Raises ModelNotConfiguredError when the
    weights file is missing; never returns a fabricated prediction."""
    import io

    import torch  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    weights_path = Path(weights_path)
    if not weights_path.is_file():
        raise ModelNotConfiguredError(
            f"Classifier weights not found at {weights_path}"
        )

    model = load_model(weights_path, device=device)
    with Image.open(io.BytesIO(image_bytes)) as pil_image:
        tensor = preprocess(pil_image)

    with torch.no_grad():
        logits = model(tensor.to(device))
        probabilities = torch.softmax(logits, dim=1)[0]

    order = torch.argsort(probabilities, descending=True)
    top = order[: max(1, top_alternatives)]
    predicted_index = int(order[0].item())
    alternatives = [
        {
            "category": CLASSES[int(i.item())],
            "probability": round(float(probabilities[i].item()), 4),
        }
        for i in top[1:]
    ]
    return {
        "predicted_category": CLASSES[predicted_index],
        "confidence": round(float(probabilities[predicted_index].item()), 4),
        "top_alternatives": alternatives,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SEVA-AI image classifier CLI")
    parser.add_argument("image", type=str, help="Path to the image file")
    parser.add_argument(
        "--weights",
        type=str,
        default=str(Path(__file__).resolve().parents[1] / "models" / "image_classifier_v1.pt"),
        help="Path to trained SEVA-AI weights",
    )
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.is_file():
        print(f"error: image not found: {image_path}", file=sys.stderr)
        return 2

    try:
        result = predict_bytes(image_path.read_bytes(), args.weights)
    except ModelNotConfiguredError as exc:
        print(f"model_not_configured: {exc}", file=sys.stderr)
        return 3

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
