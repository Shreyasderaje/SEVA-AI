"""Shared organization access helpers (used by needs and organizations APIs)."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.user import User


def get_own_organization(db: Session, user: User) -> Organization:
    """Fetch the organization owned by this user; 404 when not applied yet."""
    organization = db.scalar(
        select(Organization).where(Organization.owner_user_id == user.id)
    )
    if organization is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No organization application found. Submit one first.",
        )
    return organization
