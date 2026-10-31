"""Thin classifier wrapper around the canonical logic in `ml/src/predict_image.py`.

The backend itself has NO torch dependency: the canonical module is imported
lazily, inside `predict()`. When the weights file is missing — or PyTorch is
not installed in this environment — the wrapper reports `model_not_configured`
(addendum §10): the backend starts normally, manual category selection always
works, and no fabricated prediction is ever returned.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from app.core.config import BACKEND_DIR, get_settings

logger = logging.getLogger("seva")

PROJECT_ROOT = BACKEND_DIR.parent
ML_SRC_DIR = PROJECT_ROOT / "ml" / "src"


@dataclass(frozen=True)
class ClassifierStatus:
    configured: bool
    weights_path: Path
    reason: str | None = None


def _canonical_classes() -> tuple[str, ...]:
    """Import the canonical class list from ml/src (lazily, without torch)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "seva_predict_image", ML_SRC_DIR / "predict_image.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover — layout changed
        raise RuntimeError("ml/src/predict_image.py not found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.CLASSES)


def _torch_available() -> bool:
    try:
        import torch  # noqa: F401
        import torchvision  # noqa: F401

        return True
    except ImportError:
        return False


def _weights_file() -> Path:
    return get_settings().classifier_weights_file


def classifier_status(weights_file: Path | None = None) -> ClassifierStatus:
    """Why the classifier can or cannot run right now (no secrets logged)."""
    path = weights_file if weights_file is not None else _weights_file()
    if not path.is_file():
        return ClassifierStatus(
            configured=False,
            weights_path=path,
            reason="trained weights file not found at the configured path",
        )
    if not _torch_available():
        return ClassifierStatus(
            configured=False,
            weights_path=path,
            reason="weights exist but PyTorch/torchvision are not installed in this environment",
        )
    return ClassifierStatus(configured=True, weights_path=path, reason=None)


def predict(image_bytes: bytes) -> dict | None:
    """Run inference. Returns None when the model is not configured (the caller
    maps that to the documented `model_not_configured` response)."""
    status = classifier_status()
    if not status.configured:
        logger.info("classify skipped: %s", status.reason)
        return None

    # Lazy, path-based import of the canonical inference module — the backend
    # venv has no torch; this only executes when the runtime provides it.
    sys.path.insert(0, str(ML_SRC_DIR))
    try:
        from predict_image import ModelNotConfiguredError, predict_bytes  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover — defensive
        logger.warning("classifier runtime unavailable: %s", exc)
        return None

    try:
        return predict_bytes(image_bytes, status.weights_path)
    except ModelNotConfiguredError:
        logger.info("classify skipped: weights file disappeared")
        return None
