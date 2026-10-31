"""Shared model helpers: UUID defaults and timestamp columns."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


def new_uuid() -> str:
    return str(uuid4())


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime, nullable=False, server_default=func.now())


def updated_at_column() -> Mapped[datetime]:
    return mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
