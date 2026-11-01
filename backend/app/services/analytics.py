"""Admin analytics overview (M5 §3) — database-backed, admin-only.

All numbers come from real queries; no hardcoded values. The `days` parameter
scopes donation/offer/payment/need metrics to recent activity where
applicable (accounts and verification states are cumulative by nature and are
always shown as totals). Demo-data inclusion is reported separately so the UI
can badge aggregates that include demo records; nothing is hidden silently.
"""

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.donation import Donation, DonationCategory
from app.models.need import OrganizationNeed
from app.models.offer import DonationOffer
from app.models.organization import Organization
from app.models.support import PaymentRecord
from app.models.user import User

VALID_RANGES = (7, 30, 90, None)  # None = all time


def _since(days: int | None) -> datetime | None:
    if days is None:
        return None
    return datetime.now() - timedelta(days=days)


def _count(db: Session, statement) -> int:
    return db.scalar(statement) or 0


def compute_analytics(db: Session, days: int | None) -> dict:
    since = _since(days)

    def scoped(model_column):
        return model_column >= since if since is not None else True

    # ---- summary cards -----------------------------------------------------
    cards = {
        "total_donors": _count(
            db, select(func.count()).select_from(User).where(User.role == "donor")
        ),
        "total_organizations": _count(
            db,
            select(func.count()).select_from(User).where(User.role == "organization"),
        ),
        "verified_organizations": _count(
            db,
            select(func.count())
            .select_from(Organization)
            .where(Organization.verification_status == "verified"),
        ),
        "pending_organizations": _count(
            db,
            select(func.count())
            .select_from(Organization)
            .where(Organization.verification_status == "pending_verification"),
        ),
        "total_donations": _count(
            db,
            select(func.count())
            .select_from(Donation)
            .where(scoped(Donation.created_at)),
        ),
        "pending_donations": _count(
            db,
            select(func.count())
            .select_from(Donation)
            .where(Donation.status == "pending", scoped(Donation.created_at)),
        ),
        "completed_donations": _count(
            db,
            select(func.count())
            .select_from(Donation)
            .where(Donation.status == "completed", scoped(Donation.created_at)),
        ),
        "active_needs": _count(
            db,
            select(func.count())
            .select_from(OrganizationNeed)
            .where(OrganizationNeed.status == "active"),
        ),
        "fulfilled_needs": _count(
            db,
            select(func.count())
            .select_from(OrganizationNeed)
            .where(OrganizationNeed.status == "fulfilled"),
        ),
        "offers_sent": _count(
            db,
            select(func.count())
            .select_from(DonationOffer)
            .where(scoped(DonationOffer.created_at)),
        ),
        "offers_accepted": _count(
            db,
            select(func.count())
            .select_from(DonationOffer)
            .where(DonationOffer.status == "accepted", scoped(DonationOffer.created_at)),
        ),
        "payments_awaiting_verification": _count(
            db,
            select(func.count())
            .select_from(PaymentRecord)
            .where(PaymentRecord.status == "submitted_unverified"),
        ),
    }

    # ---- donations over time (weekly ISO buckets, bounded to the range) ----
    donation_rows = db.execute(
        select(Donation.created_at).where(scoped(Donation.created_at))
    ).all()
    weekly: dict[str, int] = {}
    for (created_at,) in donation_rows:
        iso_year, iso_week, _ = created_at.isocalendar()
        label = f"{iso_year}-W{iso_week:02d}"
        weekly[label] = weekly.get(label, 0) + 1
    donations_over_time = [
        {"week": label, "count": count} for label, count in sorted(weekly.items())
    ]

    # ---- distributions (SQL GROUP BY) --------------------------------------
    donation_status = [
        {"status": status, "count": count}
        for status, count in db.execute(
            select(Donation.status, func.count())
            .where(scoped(Donation.created_at))
            .group_by(Donation.status)
        ).all()
    ]
    donation_category = [
        {"category": code, "count": count}
        for code, count in db.execute(
            select(DonationCategory.code, func.count())
            .join(Donation, Donation.category_id == DonationCategory.id)
            .where(scoped(Donation.created_at))
            .group_by(DonationCategory.code)
        ).all()
    ]
    org_verification = [
        {"status": status, "count": count}
        for status, count in db.execute(
            select(Organization.verification_status, func.count()).group_by(
                Organization.verification_status
            )
        ).all()
    ]
    offer_outcomes = [
        {"status": status, "count": count}
        for status, count in db.execute(
            select(DonationOffer.status, func.count())
            .where(DonationOffer.status.in_(["accepted", "declined"]))
            .group_by(DonationOffer.status)
        ).all()
    ]
    needs_status = [
        {"status": status, "count": count}
        for status, count in db.execute(
            select(OrganizationNeed.status, func.count()).group_by(
                OrganizationNeed.status
            )
        ).all()
    ]

    # ---- demo-data transparency (§7.1) --------------------------------------
    demo = {
        "users": _count(
            db, select(func.count()).select_from(User).where(User.is_demo_data.is_(True))
        ),
        "donations": _count(
            db,
            select(func.count())
            .select_from(Donation)
            .where(Donation.is_demo_data.is_(True), scoped(Donation.created_at)),
        ),
        "organizations": _count(
            db,
            select(func.count())
            .select_from(Organization)
            .where(Organization.is_demo_data.is_(True)),
        ),
        "payments": _count(
            db,
            select(func.count())
            .select_from(PaymentRecord)
            .where(PaymentRecord.is_demo_data.is_(True)),
        ),
    }

    return {
        "range_days": days,
        "generated_at": datetime.now().isoformat(),
        "cards": cards,
        "donations_over_time": donations_over_time,
        "donation_status": donation_status,
        "donation_category": donation_category,
        "org_verification": org_verification,
        "offer_outcomes": offer_outcomes,
        "needs_status": needs_status,
        "demo_data": demo,
    }
