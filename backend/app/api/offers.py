"""Offer endpoints: initiation, listing, accept/decline, pickup lifecycle."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import ROLE_ADMIN, ROLE_DONOR, ROLE_ORGANIZATION
from app.core.database import get_db
from app.core.deps import get_current_active_user, require_roles
from app.models.donation import Donation
from app.models.offer import DonationOffer
from app.models.user import User
from app.schemas.common import Page
from app.services.offers import (
    accept_offer,
    decline_offer,
    get_own_offer,
    initiate_offer,
    serialize_offer,
)

router = APIRouter(prefix="/api/offers", tags=["offers"])


class DeclineRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class PickupScheduleRequest(BaseModel):
    pickup_date: str = Field(min_length=10, max_length=10)
    pickup_window_start: str
    pickup_window_end: str
    instructions: str | None = Field(default=None, max_length=1000)


def _get_own_donation(db: Session, user: User, donation_id: str) -> Donation:
    donation = db.get(Donation, donation_id)
    if donation is None or donation.donor_id != user.id:
        raise HTTPException(404, "Donation not found")
    return donation


@router.post("/initiate/{donation_id}")
def initiate(
    donation_id: str,
    request: Request,
    user: User = Depends(require_roles(ROLE_DONOR, ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    donation = db.get(Donation, donation_id)
    if donation is None or donation.donor_id != user.id:
        raise HTTPException(404, "Donation not found")
    from app.services.offers import initiate_offer

    return initiate_offer(db, donation, user, request=request)


@router.get("/mine", response_model=Page[dict])
def my_offers(
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> Page[dict]:
    from app.services.organization_access import get_own_organization

    organization = get_own_organization(db, user)
    base = select(DonationOffer).where(DonationOffer.organization_id == organization.id)
    count_query = (
        select(func.count())
        .select_from(DonationOffer)
        .where(DonationOffer.organization_id == organization.id)
    )
    if status_filter:
        if status_filter not in ("sent", "accepted", "declined", "withdrawn"):
            raise HTTPException(422, "Unknown offer status filter")
        base = base.where(DonationOffer.status == status_filter)
        count_query = count_query.where(DonationOffer.status == status_filter)
    total = db.scalar(count_query) or 0
    rows = db.scalars(
        base.order_by(DonationOffer.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[dict](
        items=[serialize_offer(db, offer, include_org=True) for offer in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/donation/{donation_id}", response_model=Page[dict])
def donation_offers(
    donation_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    user: User = Depends(require_roles(ROLE_DONOR, ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> Page[dict]:
    donation = db.get(Donation, donation_id)
    if donation is None or donation.donor_id != user.id:
        if user.role != ROLE_ADMIN:
            raise HTTPException(404, "Donation not found")
        if donation is None:
            raise HTTPException(404, "Donation not found")
    total = db.scalar(
        select(func.count())
        .select_from(DonationOffer)
        .where(DonationOffer.donation_id == donation_id)
    ) or 0
    rows = db.scalars(
        select(DonationOffer)
        .where(DonationOffer.donation_id == donation_id)
        .order_by(DonationOffer.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[dict](
        items=[serialize_offer(db, offer, include_org=True) for offer in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{offer_id}")
def get_offer(
    offer_id: str,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.offers import get_own_offer

    offer = get_own_offer(db, user, offer_id)
    return serialize_offer(db, offer, include_org=True)


@router.post("/{offer_id}/accept")
def accept(
    offer_id: str,
    request: Request,
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.offers import get_own_offer

    offer = get_own_offer(db, user, offer_id)
    return accept_offer(db, offer, user, request=request)


@router.post("/{offer_id}/decline")
def decline(
    offer_id: str,
    request: Request,
    payload: DeclineRequest | None = None,
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.offers import get_own_offer

    offer = get_own_offer(db, user, offer_id)
    reason = payload.reason if payload else None
    return decline_offer(db, offer, user, reason, request=request)


@router.post("/{offer_id}/pickup")
def schedule_pickup(
    offer_id: str,
    request: Request,
    payload: PickupScheduleRequest,
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.pickup import schedule_pickup

    try:
        pickup_date = datetime.strptime(payload.pickup_date, "%Y-%m-%d").date()
        window_start = datetime.fromisoformat(payload.pickup_window_start)
        window_end = datetime.fromisoformat(payload.pickup_window_end)
    except ValueError as exc:
        raise HTTPException(422, f"Invalid date/time format: {exc}") from exc
    return schedule_pickup(
        db,
        offer_id,
        user,
        pickup_date=pickup_date,
        window_start=window_start,
        window_end=window_end,
        instructions=payload.instructions,
        request=request,
    )


@router.post("/{offer_id}/picked-up")
def mark_picked_up(
    offer_id: str,
    request: Request,
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.pickup import mark_picked_up as _mark_picked_up

    return _mark_picked_up(db, offer_id, user, request=request)


class CompletionRequest(BaseModel):
    quantity_received: float = Field(gt=0)


@router.post("/{offer_id}/complete")
def complete(
    offer_id: str,
    request: Request,
    payload: CompletionRequest,
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.pickup import complete_offer

    return complete_offer(
        db, offer_id, user, quantity_received=payload.quantity_received, request=request
    )
