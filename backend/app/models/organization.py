"""Organizations and their verification documents."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.common import created_at_column, new_uuid, updated_at_column
from app.models.base import Base


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('pending_verification', 'verified', 'rejected', 'suspended')",
            name="verification_status_valid",
        ),
        CheckConstraint(
            "upi_status IN ('none', 'pending_approval', 'approved', 'rejected')",
            name="upi_status_valid",
        ),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="latitude_range_valid",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="longitude_range_valid",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    org_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    representative_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending_verification"
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    upi_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    upi_qr_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    upi_status: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[created_at_column] = created_at_column()  # type: ignore[valid-type]
    updated_at: Mapped[updated_at_column] = updated_at_column()  # type: ignore[valid-type]


class OrganizationDocument(Base):
    __tablename__ = "organization_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default="CURRENT_TIMESTAMP"
    )
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
