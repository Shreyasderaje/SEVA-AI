"""Model registry: versions of trained models and their evaluations."""

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.common import created_at_column, new_uuid
from app.models.base import Base


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('image_classifier', 'acceptance_model')", name="kind_valid"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    kind: Mapped[str] = mapped_column(String(25), nullable=False)
    artifact_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[created_at_column] = created_at_column()  # type: ignore[valid-type]


class ModelEvaluation(Base):
    __tablename__ = "model_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    model_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("model_versions.id"), nullable=False
    )
    split: Mapped[str] = mapped_column(String(20), nullable=False)
    metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[created_at_column] = created_at_column()  # type: ignore[valid-type]
