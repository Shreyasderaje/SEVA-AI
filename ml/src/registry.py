"""Shared model registry helpers: insert trained models and evaluations into
the backend database (`model_versions`, `model_evaluations` tables).

Used by train_image_classifier.py (--register) and
evaluate_image_classifier.py (--register). The backend app is imported from
the backend directory; the ML pipeline remains independent of it otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ML_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ML_DIR.parent / "backend"
# Script-mode Python adds the script's own directory to sys.path, not the CWD —
# make the backend package importable before any `app.*` import below.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _backend_models():
    from app.models.ml import ModelEvaluation, ModelVersion  # noqa: PLC0415

    return ModelVersion, ModelEvaluation


def ensure_model_version(
    *,
    model_name: str,
    version: str,
    kind: str,
    artifact_path: str,
    seed: int,
    metadata: dict,
) -> str:
    """Insert (or reuse) a model_versions row; returns the row id."""
    from app.core.database import SessionLocal  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    ModelVersion, _ = _backend_models()
    session = SessionLocal()
    try:
        existing = session.scalar(
            select(ModelVersion).where(
                ModelVersion.model_name == model_name,
                ModelVersion.version == version,
                ModelVersion.kind == kind,
            )
        )
        if existing is not None:
            print(f"model_versions: '{model_name} {version}' already registered (id={existing.id})")
            return existing.id
        row = ModelVersion(
            model_name=model_name,
            version=version,
            kind=kind,
            artifact_path=artifact_path,
            seed=seed,
            metadata_json=json.dumps(metadata),
            is_active=True,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        print(f"model_versions: registered '{model_name} {version}' (id={row.id})")
        return row.id
    finally:
        session.close()


def register_evaluation(
    *,
    model_version_id: str,
    split: str,
    metrics: dict,
    report_path: str,
    is_demo_data: bool = False,
) -> str:
    """Insert a model_evaluations row; returns the row id."""
    from app.core.database import SessionLocal  # noqa: PLC0415

    _, ModelEvaluation = _backend_models()
    session = SessionLocal()
    try:
        row = ModelEvaluation(
            model_version_id=model_version_id,
            split=split,
            metrics_json=json.dumps(metrics),
            report_path=report_path,
            is_demo_data=is_demo_data,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        print(f"model_evaluations: registered evaluation (id={row.id})")
        return row.id
    finally:
        session.close()
