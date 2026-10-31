"""Donation taxonomy (fixed classifier classes + admin-managed display
subcategories), donations, and donation images."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.common import created_at_column, new_uuid, updated_at_column
from app.models.base import Base


class DonationCategory(Base):
    """The five FIXED classifier output classes. Admins may not rename, delete,
    or deactivate these in a way that breaks model inference (addendum §3)."""

    __tablename__ = "donation_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DonationSubcategory(Base):
    """Admin-added DISPLAY subcategories. These never become classifier classes."""

    __tablename__ = "donation_subcategories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("donation_categories.id"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[created_at_column] = created_at_column()  # type: ignore[valid-type]
    updated_at: Mapped[updated_at_column] = updated_at_column()  # type: ignore[valid-type]


class DonationCompatibility(Base):
    """Allowed related-category mapping used by the matching engine."""

    __tablename__ = "donation_compatibility"
    __table_args__ = (
        CheckConstraint("factor IN ('exact', 'related')", name="factor_valid"),
    )

    donation_category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("donation_categories.id"), primary_key=True
    )
    need_category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("donation_categories.id"), primary_key=True
    )
    factor: Mapped[str] = mapped_column(String(10), nullable=False)


class Donation(Base):
    __tablename__ = "donations"
    __table_args__ = (
        CheckConstraint(
            "unit IN ('kg', 'pieces', 'packets', 'sets', 'litres')", name="unit_valid"
        ),
        CheckConstraint(
            "condition IS NULL OR condition IN ('new', 'good', 'fair')",
            name="condition_valid",
        ),
        CheckConstraint(
            "status IN ('pending', 'offered', 'accepted', 'pickup_scheduled', "
            "'picked_up', 'completed', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "pickup_latitude IS NULL OR (pickup_latitude >= -90 AND pickup_latitude <= 90)",
            name="pickup_latitude_range_valid",
        ),
        CheckConstraint(
            "pickup_longitude IS NULL OR (pickup_longitude >= -180 AND pickup_longitude <= 180)",
            name="pickup_longitude_range_valid",
        ),
        Index("ix_donations_donor_created", "donor_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    reference: Mapped[str] = mapped_column(String(24), unique=True, index=True, nullable=False)
    donor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    # Operative category = the DONOR-CONFIRMED category (addendum §4: AI
    # prediction is stored separately, never used without explicit confirmation).
    category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("donation_categories.id"), nullable=False
    )
    subcategory_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("donation_subcategories.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(10), nullable=False)
    condition: Mapped[str | None] = mapped_column(String(10), nullable=True)
    pickup_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pickup_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    pickup_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pickup_window_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pickup_window_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Raw model output (one of the five class codes) — nullable, never fabricated.
    ai_predicted_category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    flag_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[created_at_column] = created_at_column()  # type: ignore[valid-type]
    updated_at: Mapped[updated_at_column] = updated_at_column()  # type: ignore[valid-type]


class DonationImage(Base):
    __tablename__ = "donation_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    donation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("donations.id"), nullable=False
    )
    stored_path: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(40), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[created_at_column] = created_at_column()  # type: ignore[valid-type]

    __table_args__ = (
        UniqueConstraint("donation_id", "position", name="uq_donation_images_donation_position"),
    )
