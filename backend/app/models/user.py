"""User accounts and donor profiles."""

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import ACCOUNT_STATUSES, USER_ROLES
from app.models.common import created_at_column, new_uuid, updated_at_column
from app.models.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('donor', 'organization', 'admin')", name="role_valid"
        ),
        CheckConstraint(
            "status IN ('active', 'inactive', 'suspended')", name="status_valid"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="donor")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # Addendum correction #2: demo-data flag on all seedable tables.
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[created_at_column] = created_at_column()  # type: ignore[valid-type]
    updated_at: Mapped[updated_at_column] = updated_at_column()  # type: ignore[valid-type]


class DonorProfile(Base):
    __tablename__ = "donor_profiles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), primary_key=True
    )
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    preferred_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[created_at_column] = created_at_column()  # type: ignore[valid-type]
    updated_at: Mapped[updated_at_column] = updated_at_column()  # type: ignore[valid-type]
