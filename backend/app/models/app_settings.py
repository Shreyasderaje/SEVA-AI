"""Key/value settings table (matching weights, service radius, admin flags)."""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.common import updated_at_column
from app.models.base import Base


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[updated_at_column] = updated_at_column()  # type: ignore[valid-type]
