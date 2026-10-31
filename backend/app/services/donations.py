"""Donation domain services: references, status history, access checks."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import ROLE_ADMIN
from app.models.donation import Donation
from app.models.offer import DonationStatusHistory


def next_reference(db: Session) -> str:
    """Human-readable unique reference, e.g. SEVA-2026-000123 (§6.2).

    Sequence restarts per calendar year; the unique constraint on `reference`
    plus a retry in the caller protects against concurrent creation races.
    """
    year_prefix = f"SEVA-{datetime.now().year}-"
    count = (
        db.scalar(
            select(func.count())
            .select_from(Donation)
            .where(Donation.reference.like(f"{year_prefix}%"))
        )
        or 0
    )
    return f"{year_prefix}{count + 1:06d}"


def record_status_transition(
    db: Session,
    donation: Donation,
    *,
    to_status: str,
    actor_user_id: str | None,
    note: str | None = None,
) -> bool:
    """Append one history row and move the donation's overall status.

    Addendum §1: no duplicate history rows are written when the overall status
    has not changed. Returns True when a transition actually happened.
    """
    if donation.status == to_status:
        return False
    db.add(
        DonationStatusHistory(
            donation_id=donation.id,
            actor_user_id=actor_user_id,
            from_status=donation.status,
            to_status=to_status,
            note=note[:500] if note else None,
        )
    )
    donation.status = to_status
    return True


def can_view_donation(user, donation: Donation) -> bool:
    """Donor sees own donations; admin sees all. Organizations gain access to
    donations they hold offers on in M4."""
    return user.role == ROLE_ADMIN or donation.donor_id == user.id
