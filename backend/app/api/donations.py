"""Donation management: create (donor), list/detail (owner or admin),
cancel (owner, pending/offered only), dashboard summary counts.

Addendum rules enforced here:
- 1–3 photographs; the FIRST is the primary classification image (§4).
- AI-predicted category stored separately from the donor-confirmed category.
- Coordinates stored only with explicit consent; ranges validated (§6).
- Donor cancellation allowed only while pending/offered (§1, §7).
- One append-only history row per actual overall-status change (§1).
"""

from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import (
    ACCOUNT_ACTIVE,
    DONATION_CANCELLED,
    DONATION_OFFERED,
    DONATION_PENDING,
    ROLE_ADMIN,
    ROLE_DONOR,
)
from app.core.database import get_db
from app.core.deps import require_roles
from app.core.rate_limit import limiter
from app.models.donation import Donation, DonationCategory, DonationImage, DonationSubcategory
from app.models.offer import DonationStatusHistory
from app.models.user import User
from app.schemas.common import Page
from app.schemas.donation import (
    DonationDetailOut,
    DonationHistoryOut,
    DonationImageOut,
    DonationSummaryCounts,
    DonationSummaryOut,
)
from app.services.audit import log_audit
from app.services.donations import next_reference, record_status_transition
from app.services.storage import save_donation_image

router = APIRouter(prefix="/api/donations", tags=["donations"])

UNIT = Literal["kg", "pieces", "packets", "sets", "litres"]
CONDITION = Literal["new", "good", "fair"]
CLASS_CODES = Literal["clothing", "grains_rice", "packaged_food", "utensils", "other"]
MAX_IMAGES = 3


def _get_category(db: Session, category_id: str) -> DonationCategory:
    category = db.get(DonationCategory, category_id)
    if category is None or not category.is_active:
        raise HTTPException(422, "Unknown or inactive category")
    return category


def _validate_geometry(
    pickup_latitude: float | None,
    pickup_longitude: float | None,
    location_consent: bool,
) -> None:
    if (pickup_latitude is None) != (pickup_longitude is None):
        raise HTTPException(422, "Latitude and longitude must be provided together")
    if pickup_latitude is None:
        if location_consent:
            raise HTTPException(422, "Consent is only meaningful with coordinates")
        return
    if not location_consent:
        raise HTTPException(
            422, "Explicit consent is required to store pickup coordinates"
        )
    if not (-90 <= pickup_latitude <= 90):
        raise HTTPException(422, "Latitude must be between -90 and 90")
    if not (-180 <= pickup_longitude <= 180):
        raise HTTPException(422, "Longitude must be between -180 and 180")


def _validate_window(start: datetime | None, end: datetime | None) -> None:
    if (start is None) != (end is None):
        raise HTTPException(422, "Pickup window start and end must be provided together")
    if start is not None and end is not None and end <= start:
        raise HTTPException(422, "Pickup window end must be after its start")


def _serialize_summary(db: Session, donation: Donation) -> DonationSummaryOut:
    primary = donation.images[0] if donation.images else None
    return DonationSummaryOut(
        id=donation.id,
        reference=donation.reference,
        title=donation.title,
        status=donation.status,  # type: ignore[arg-type]
        quantity=donation.quantity,
        unit=donation.unit,
        category_code=donation.category.code,
        category_display_name=donation.category.display_name,
        subcategory_display_name=(
            donation.subcategory.display_name if donation.subcategory else None
        ),
        ai_predicted_category=donation.ai_predicted_category,
        ai_confidence=donation.ai_confidence,
        primary_image_url=f"/api/images/{primary.id}" if primary else None,
        created_at=donation.created_at,
    )


def _serialize_detail(db: Session, donation: Donation) -> DonationDetailOut:
    return DonationDetailOut(
        **_serialize_summary(db, donation).model_dump(),
        description=donation.description,
        condition=donation.condition,
        pickup_area=donation.pickup_area,
        pickup_latitude=donation.pickup_latitude,
        pickup_longitude=donation.pickup_longitude,
        location_consent=donation.location_consent,
        pickup_window_start=donation.pickup_window_start,
        pickup_window_end=donation.pickup_window_end,
        images=[
            DonationImageOut(
                id=image.id,
                position=image.position,
                mime_type=image.mime_type,
                size_bytes=image.size_bytes,
                url=f"/api/images/{image.id}",
            )
            for image in donation.images
        ],
        timeline=[
            DonationHistoryOut.model_validate(row)
            for row in db.scalars(
                select(DonationStatusHistory)
                .where(DonationStatusHistory.donation_id == donation.id)
                .order_by(DonationStatusHistory.created_at.asc())
            ).all()
        ],
    )


@router.post("", response_model=DonationDetailOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_settings().rate_limit_login)
async def create_donation(
    request: Request,
    title: Annotated[str, Form(min_length=3, max_length=150)],
    description: Annotated[str | None, Form(max_length=2000)] = None,
    category_id: Annotated[str, Form()] = "",
    subcategory_id: Annotated[str | None, Form()] = None,
    quantity: Annotated[float, Form(gt=0)] = 1.0,
    unit: Annotated[UNIT, Form()] = "pieces",
    condition: Annotated[CONDITION | None, Form()] = None,
    pickup_area: Annotated[str, Form(min_length=2, max_length=255)] = "",
    pickup_latitude: Annotated[float | None, Form()] = None,
    pickup_longitude: Annotated[float | None, Form()] = None,
    location_consent: Annotated[bool, Form()] = False,
    pickup_window_start: Annotated[datetime | None, Form()] = None,
    pickup_window_end: Annotated[datetime | None, Form()] = None,
    ai_predicted_category: Annotated[CLASS_CODES | None, Form()] = None,
    ai_confidence: Annotated[float | None, Form(ge=0, le=1)] = None,
    images: Annotated[list[UploadFile], File()] = [],
    user=Depends(require_roles(ROLE_DONOR)),
    db: Session = Depends(get_db),
) -> JSONResponse:
    if user.status != ACCOUNT_ACTIVE:
        raise HTTPException(403, "Account is not active")

    category = _get_category(db, category_id)

    subcategory = None
    if subcategory_id:
        subcategory = db.get(DonationSubcategory, subcategory_id)
        if subcategory is None or not subcategory.is_active:
            raise HTTPException(422, "Unknown or inactive subcategory")
        if subcategory.category_id != category.id:
            raise HTTPException(422, "Subcategory does not belong to the selected category")

    _validate_geometry(pickup_latitude, pickup_longitude, location_consent)
    _validate_window(pickup_window_start, pickup_window_end)

    if (ai_predicted_category is None) != (ai_confidence is None):
        raise HTTPException(
            422, "ai_predicted_category and ai_confidence must be provided together"
        )

    if not 1 <= len(images) <= MAX_IMAGES:
        raise HTTPException(
            422, f"Provide between 1 and {MAX_IMAGES} photographs"
        )

    donation = Donation(
        reference=next_reference(db),
        donor_id=user.id,
        category_id=category.id,
        subcategory_id=subcategory.id if subcategory else None,
        title=title.strip(),
        description=description.strip() if description else None,
        quantity=quantity,
        unit=unit,
        condition=condition,
        pickup_area=pickup_area.strip(),
        pickup_latitude=pickup_latitude,
        pickup_longitude=pickup_longitude,
        location_consent=location_consent,
        pickup_window_start=pickup_window_start,
        pickup_window_end=pickup_window_end,
        ai_predicted_category=ai_predicted_category,
        ai_confidence=ai_confidence,
        status=DONATION_PENDING,
    )
    db.add(donation)
    db.flush()  # assigns donation.id for the storage layout

    # The FIRST image is the primary classification image (addendum §4).
    try:
        for position, upload in enumerate(images, start=1):
            stored = await save_donation_image(upload, donation.id)
            db.add(
                DonationImage(
                    donation_id=donation.id,
                    stored_path=stored.stored_path,
                    original_filename_hash=None,  # filenames are discarded (§6.5)
                    mime_type=stored.mime_type,
                    size_bytes=stored.size_bytes,
                    position=position,
                )
            )
    except HTTPException:
        db.rollback()  # no orphan files or partial rows on a failed upload
        raise

    # Creation row of the append-only history (None -> pending).
    db.add(
        DonationStatusHistory(
            donation_id=donation.id,
            actor_user_id=user.id,
            from_status=None,
            to_status=DONATION_PENDING,
        )
    )
    log_audit(
        db,
        actor_user_id=user.id,
        action="donation.create",
        target_type="donation",
        target_id=donation.id,
        note=f"Donation {donation.reference} created",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(donation)
    # slowapi requires rate-limited endpoints to return a Starlette Response.
    detail = _serialize_detail(db, donation)
    return JSONResponse(status_code=201, content=detail.model_dump(mode="json"))


@router.get("/summary", response_model=DonationSummaryCounts)
def donation_summary(
    user=Depends(require_roles(ROLE_DONOR)),
    db: Session = Depends(get_db),
) -> DonationSummaryCounts:
    rows = db.execute(
        select(Donation.status, func.count())
        .where(Donation.donor_id == user.id)
        .group_by(Donation.status)
    ).all()
    counts = {status_value: count for status_value, count in rows}
    return DonationSummaryCounts(
        active=counts.get("pending", 0) + counts.get("offered", 0),
        accepted=counts.get("accepted", 0)
        + counts.get("pickup_scheduled", 0)
        + counts.get("picked_up", 0),
        completed=counts.get("completed", 0),
        total=sum(counts.values()),
    )


@router.get("", response_model=Page[DonationSummaryOut])
def list_donations(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    category_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    user=Depends(require_roles(ROLE_DONOR)),
    db: Session = Depends(get_db),
) -> Page[DonationSummaryOut]:
    query = select(Donation).where(Donation.donor_id == user.id)
    count_query = select(func.count()).select_from(Donation).where(Donation.donor_id == user.id)

    if status_filter:
        if status_filter not in (
            "pending", "offered", "accepted", "pickup_scheduled",
            "picked_up", "completed", "cancelled",
        ):
            raise HTTPException(422, "Unknown status filter")
        query = query.where(Donation.status == status_filter)
        count_query = count_query.where(Donation.status == status_filter)
    if category_id:
        query = query.where(Donation.category_id == category_id)
        count_query = count_query.where(Donation.category_id == category_id)
    if date_from:
        query = query.where(Donation.created_at >= datetime.combine(date_from, datetime.min.time()))
        count_query = count_query.where(
            Donation.created_at >= datetime.combine(date_from, datetime.min.time())
        )
    if date_to:
        upper = datetime.combine(date_to + timedelta(days=1), datetime.min.time())
        query = query.where(Donation.created_at < upper)
        count_query = count_query.where(Donation.created_at < upper)
    if q:
        pattern = f"%{q.lower()}%"
        query = query.where(func.lower(Donation.title).like(pattern))
        count_query = count_query.where(func.lower(Donation.title).like(pattern))

    total = db.scalar(count_query) or 0
    rows = db.scalars(
        query.order_by(Donation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[DonationSummaryOut](
        items=[_serialize_summary(db, d) for d in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{donation_id}", response_model=DonationDetailOut)
def get_donation(
    donation_id: str,
    user=Depends(require_roles(ROLE_DONOR, ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> DonationDetailOut:
    donation = db.get(Donation, donation_id)
    if donation is None or not _can_view(user, donation):
        raise HTTPException(404, "Donation not found")
    return _serialize_detail(db, donation)


@router.post("/{donation_id}/cancel", response_model=DonationDetailOut)
def cancel_donation(
    donation_id: str,
    user=Depends(require_roles(ROLE_DONOR)),
    db: Session = Depends(get_db),
) -> DonationDetailOut:
    donation = db.get(Donation, donation_id)
    if donation is None or donation.donor_id != user.id:
        raise HTTPException(404, "Donation not found")
    if donation.status not in (DONATION_PENDING, DONATION_OFFERED):
        raise HTTPException(
            409, f"A donation can only be cancelled while pending or offered "
            f"(current status: {donation.status})"
        )
    record_status_transition(
        db,
        donation,
        to_status=DONATION_CANCELLED,
        actor_user_id=user.id,
        note="Cancelled by donor",
    )
    log_audit(
        db,
        actor_user_id=user.id,
        action="donation.cancel",
        target_type="donation",
        target_id=donation.id,
        note=f"Donation {donation.reference} cancelled by donor",
    )
    db.commit()
    db.refresh(donation)
    return _serialize_detail(db, donation)


def _can_view(user, donation: Donation) -> bool:
    return user.role == ROLE_ADMIN or donation.donor_id == user.id


@router.get("/{donation_id}/matches")
def donation_matches(
    donation_id: str,
    user: User = Depends(require_roles(ROLE_DONOR, ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    """Explainable eligibility + ranking for this donation (§6.4).

    Read-only: the offer workflow belongs to M4. Scoring uses the
    donor-confirmed category from the database; client-supplied AI fields are
    never consulted.
    """
    donation = db.get(Donation, donation_id)
    if donation is None or not _can_view(user, donation):
        raise HTTPException(404, "Donation not found")
    from app.services.matching import MatchingInputError, compute_matches

    try:
        return compute_matches(db, donation)
    except MatchingInputError as exc:
        raise HTTPException(409, str(exc)) from exc
