"""Donation offers and the immutable donation status history.

Addendum corrections #1 and #9: an organization's response is an OFFER-level
record; a decline never rejections the whole donation. Offer statuses exclude
`expired` (no scheduler exists in this release). `quantity_received` is stored
on the accepted offer (addendum correction #5).
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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


class DonationOffer(Base):
    __tablename__ = "donation_offers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('sent', 'accepted', 'declined', 'withdrawn')",
            name="status_valid",
        ),
        # Never re-offer the same donation to the same organization (addendum §9).
        UniqueConstraint("donation_id", "organization_id", name="uq_offers_donation_org"),
        Index("ix_donation_offers_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    donation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("donations.id"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False
    )
    need_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organization_needs.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="sent")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rank_at_offer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Matching factor values + explanation snapshot at the time the offer was sent.
    factor_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    decline_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Actual quantity received, validated > 0 and <= quantity offered (addendum §5).
    quantity_received: Mapped[float | None] = mapped_column(Float, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # M4: the organization's confirmed pickup plan (donor's preferred window
    # lives on `donations`).
    pickup_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    pickup_window_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pickup_window_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pickup_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[created_at_column] = created_at_column()  # type: ignore[valid-type]
    updated_at: Mapped[updated_at_column] = updated_at_column()  # type: ignore[valid-type]


class DonationStatusHistory(Base):
    """Append-only history of OVERALL donation status changes. Offer-level
    accept/decline events live on the offer row and in the audit log (§1)."""

    __tablename__ = "donation_status_history"
    __table_args__ = (
        Index(
            "ix_donation_status_history_donation_created", "donation_id", "created_at"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    donation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("donations.id"), nullable=False
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Monotonic per-donation sequence: created_at has second precision on some
    # platforms, so the timeline needs a stable tie-breaker.
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[created_at_column] = created_at_column()  # type: ignore[valid-type]
