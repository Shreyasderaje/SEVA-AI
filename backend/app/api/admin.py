"""Admin-only endpoints. M1 exposes the user list (real functionality used by
the M5 admin dashboard); verification queues and dashboards come later."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import ROLE_ADMIN
from app.core.database import get_db
from app.core.deps import require_roles
from app.models.user import User
from app.schemas.auth import UserOut
from app.services.analytics import compute_analytics
from app.schemas.common import Page

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)


@router.get("/users", response_model=Page[UserOut])
def list_users(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[UserOut]:
    total = db.scalar(select(func.count()).select_from(User)) or 0
    rows = db.scalars(
        select(User)
        .order_by(User.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/donations", response_model=Page[dict])
def admin_list_donations(
    status_filter: str | None = Query(default=None, alias="status"),
    category_id: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    user: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> Page[dict]:
    """Read-only donation list for admins (§5.4) with filters + pagination."""
    from app.core.constants import DONATION_STATUSES
    from app.models.donation import Donation, DonationCategory

    query = select(Donation)
    count_query = select(func.count()).select_from(Donation)
    if status_filter:
        if status_filter not in DONATION_STATUSES:
            raise HTTPException(422, "Unknown status filter")
        query = query.where(Donation.status == status_filter)
        count_query = count_query.where(Donation.status == status_filter)
    if category_id:
        query = query.where(Donation.category_id == category_id)
        count_query = count_query.where(Donation.category_id == category_id)
    if q:
        pattern = f"%{q.lower()}%"
        query = query.where(
            func.lower(Donation.title).like(pattern)
            | func.lower(Donation.reference).like(pattern)
        )
        count_query = count_query.where(
            func.lower(Donation.title).like(pattern)
            | func.lower(Donation.reference).like(pattern)
        )
    total = db.scalar(count_query) or 0
    rows = db.scalars(
        query.order_by(Donation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = []
    for donation in rows:
        category = db.get(DonationCategory, donation.category_id)
        items.append(
            {
                "id": donation.id,
                "reference": donation.reference,
                "title": donation.title,
                "status": donation.status,
                "quantity": donation.quantity,
                "unit": donation.unit,
                "category_code": category.code if category else None,
                "is_demo": donation.is_demo_data,
                "created_at": donation.created_at.isoformat(),
            }
        )
    return Page[dict](items=items, total=total, page=page, page_size=page_size)


@router.get("/analytics")
def admin_analytics(
    days: int | None = Query(default=None),
    user: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    """Admin analytics overview — DB-backed, admin-only (§3)."""
    from app.services.analytics import VALID_RANGES

    if days is not None and days not in VALID_RANGES:
        raise HTTPException(422, "Unsupported range. Use one of: 7, 30, 90, or omit for all time.")
    return compute_analytics(db, days)
