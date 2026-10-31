"""Notifications, payment records, and the append-only audit log."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.common import created_at_column, new_uuid
from app.models.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Monotonic per-user sequence — stable tie-breaker for list ordering.
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[created_at_column] = created_at_column()  # type: ignore[valid-type]

    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read_at"),)


class PaymentRecord(Base):
    """Manual-verification UPI payment reference (§6.8). Never stores payment
    secrets; a QR scan is never treated as proof of payment."""

    __tablename__ = "payment_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('submitted_unverified', 'verified', 'rejected')",
            name="status_valid",
        ),
        CheckConstraint("amount IS NULL OR amount > 0", name="amount_positive"),
        Index("ix_payment_records_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    donor_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False
    )
    donation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    transaction_reference: Mapped[str] = mapped_column(String(40), nullable=False)
    receipt_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(25), nullable=False, default="submitted_unverified")
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[created_at_column] = created_at_column()  # type: ignore[valid-type]


class AuditLog(Base):
    """Append-only at the application level. Stores actor, action, target,
    timestamp, short note, and an optional hashed IP."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[created_at_column] = created_at_column()  # type: ignore[valid-type]

    __table_args__ = (Index("ix_audit_logs_created_at", "created_at"),)
