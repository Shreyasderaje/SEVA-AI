"""Organization needs board."""

from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.common import created_at_column, new_uuid, updated_at_column
from app.models.base import Base


class OrganizationNeed(Base):
    __tablename__ = "organization_needs"
    __table_args__ = (
        CheckConstraint(
            "urgency IN ('low', 'medium', 'high', 'critical')", name="urgency_valid"
        ),
        CheckConstraint(
            "status IN ('active', 'paused', 'closed', 'fulfilled')", name="status_valid"
        ),
        CheckConstraint(
            "unit IN ('kg', 'pieces', 'packets', 'sets', 'litres')", name="unit_valid"
        ),
        CheckConstraint("quantity_required > 0", name="quantity_required_positive"),
        # The fulfilled quantity must never exceed the required quantity
        # (addendum correction #5).
        CheckConstraint(
            "quantity_fulfilled >= 0 AND quantity_fulfilled <= quantity_required",
            name="quantity_fulfilled_bounds",
        ),
        Index("ix_organization_needs_org_status", "organization_id", "status"),
        Index("ix_organization_needs_category_status", "category_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False
    )
    category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("donation_categories.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity_required: Mapped[float] = mapped_column(Float, nullable=False)
    quantity_fulfilled: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    urgency: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    required_by: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[created_at_column] = created_at_column()  # type: ignore[valid-type]
    updated_at: Mapped[updated_at_column] = updated_at_column()  # type: ignore[valid-type]
