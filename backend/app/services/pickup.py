"""Pickup scheduling, picked-up, and completion (M4 §8).

Completion is transactional and idempotent:
- the donation moves picked_up → completed under a status guard, so repeated
  requests fail instead of double-counting;
- the need's fulfilled quantity is incremented by
  min(quantity_received, remaining) under a conditional UPDATE, so concurrent
  completions can never over-fulfil (CHECK constraint backs this up);
- `quantity_received` is stored on the offer — the ACTUAL amount received,
  validated > 0 and ≤ the donated quantity.
"""

from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.constants import (
    DONATION_ACCEPTED,
    DONATION_COMPLETED,
    DONATION_PICKED_UP,
    DONATION_PICKUP_SCHEDULED,
    NEED_FULFILLED,
    OFFER_ACCEPTED,
)
from app.models.donation import Donation
from app.models.need import OrganizationNeed
from app.models.offer import DonationOffer
from app.models.organization import Organization
from app.services import notifications
from app.services.audit import log_audit
from app.services.offers import _org_id_for_user, record_transition, serialize_offer


def _load_accepted_offer(db: Session, offer_id: str, user) -> tuple[DonationOffer, Donation]:
    offer = db.get(DonationOffer, offer_id)
    if offer is None:
        raise HTTPException(404, "Offer not found")
    if offer.status != OFFER_ACCEPTED:
        raise HTTPException(409, f"Only accepted offers support this action (current: {offer.status})")
    organization_id = _org_id_for_user(db, user)
    if offer.organization_id != organization_id:
        raise HTTPException(403, "This offer is addressed to another organization")
    donation = db.get(Donation, offer.donation_id)
    if donation is None:
        raise HTTPException(404, "Donation not found")
    return offer, donation


def schedule_pickup(
    db: Session,
    offer_id: str,
    user,
    *,
    pickup_date: date,
    window_start: datetime,
    window_end: datetime,
    instructions: str | None,
    request=None,
) -> dict:
    offer, donation = _load_accepted_offer(db, offer_id, user)
    if donation.status != DONATION_ACCEPTED:
        raise HTTPException(
            409, f"Pickup can only be scheduled on an accepted donation (current: {donation.status})"
        )
    if window_end <= window_start:
        raise HTTPException(422, "The pickup window end must be after its start")

    offer.pickup_date = pickup_date
    offer.pickup_window_start = window_start
    offer.pickup_window_end = window_end
    offer.pickup_instructions = (instructions or "").strip() or None

    moved = record_transition(
        db,
        donation,
        to_status=DONATION_PICKUP_SCHEDULED,
        actor_user_id=user.id,
        note=f"Pickup scheduled for {pickup_date.isoformat()}",
    )
    if moved:
        notifications.notify(
            db,
            user_id=donation.donor_id,
            type="pickup_scheduled",
            title=f"Pickup scheduled: {donation.title}",
            body=f"{pickup_date.isoformat()} {window_start.strftime('%H:%M')}–{window_end.strftime('%H:%M')}."
            + (f" Instructions: {instructions.strip()}" if instructions and instructions.strip() else ""),
            link=f"/donations/{donation.id}",
        )
    notifications.notify(
        db,
        user_id=_org_owner(db, offer),
        type="pickup_scheduled_org",
        title="Pickup scheduled",
        body=f"Donation {donation.reference} — {pickup_date.isoformat()}.",
        link="/organization/offers",
    )
    log_audit(
        db,
        actor_user_id=user.id,
        action="offer.pickup_scheduled",
        target_type="offer",
        target_id=offer.id,
        note=f"Pickup {pickup_date.isoformat()} for {donation.reference}",
        ip=getattr(request, "client", None) and request.client.host,
    )
    db.commit()
    db.refresh(offer)
    return serialize_offer(db, offer)


def _org_owner(db: Session, offer: DonationOffer) -> str:
    organization = db.get(Organization, offer.organization_id)
    return organization.owner_user_id if organization else ""


def mark_picked_up(db: Session, offer_id: str, user, request=None) -> dict:
    offer, donation = _load_accepted_offer(db, offer_id, user)
    if donation.status != DONATION_PICKUP_SCHEDULED:
        raise HTTPException(
            409,
            f"Pickup can only be marked after scheduling (current: {donation.status})",
        )
    moved = record_transition(
        db, donation, to_status=DONATION_PICKED_UP, actor_user_id=user.id,
        note="Donation picked up by the organization",
    )
    if moved:
        notifications.notify(
            db,
            user_id=donation.donor_id,
            type="picked_up",
            title=f"Donation picked up: {donation.title}",
            body=f"{donation.reference} was picked up. Completion follows once processed.",
            link=f"/donations/{donation.id}",
        )
    log_audit(
        db,
        actor_user_id=user.id,
        action="offer.picked_up",
        target_type="offer",
        target_id=offer.id,
        note=f"Donation {donation.reference} picked up",
        ip=getattr(request, "client", None) and request.client.host,
    )
    db.commit()
    db.refresh(offer)
    return serialize_offer(db, offer)


def complete_offer(
    db: Session,
    offer_id: str,
    user,
    *,
    quantity_received: float,
    request=None,
) -> dict:
    offer, donation = _load_accepted_offer(db, offer_id, user)
    if donation.status != DONATION_PICKED_UP:
        raise HTTPException(
            409,
            f"Completion requires the picked_up state (current: {donation.status})",
        )
    if quantity_received <= 0:
        raise HTTPException(422, "Received quantity must be greater than zero")
    if quantity_received > donation.quantity:
        raise HTTPException(
            422,
            f"Received quantity cannot exceed the donated quantity "
            f"({donation.quantity:.4g} {donation.unit}).",
        )

    need = db.get(OrganizationNeed, offer.need_id) if offer.need_id else None

    # Donation completion is guarded: a repeated request hits the status guard
    # and fails instead of double-counting (idempotency by state machine).
    # The history row is written FIRST — the bulk update below synchronizes the
    # in-memory status and record_transition would otherwise skip it.
    record_transition(
        db, donation, to_status=DONATION_COMPLETED, actor_user_id=user.id,
        note=f"Completed; received {quantity_received:.4g} {donation.unit}",
    )
    donation_update = db.execute(
        update(Donation)
        .where(Donation.id == donation.id, Donation.status == DONATION_PICKED_UP)
        .values(status=DONATION_COMPLETED)
    )
    if donation_update.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "This donation has already been completed.")
    offer.quantity_received = quantity_received

    need_note = None
    if need is not None:
        delta = min(quantity_received, need.remaining_quantity)
        if delta > 0:
            need_update = db.execute(
                update(OrganizationNeed)
                .where(
                    OrganizationNeed.id == need.id,
                    OrganizationNeed.quantity_fulfilled + delta
                    <= OrganizationNeed.quantity_required,
                )
                .values(quantity_fulfilled=OrganizationNeed.quantity_fulfilled + delta)
            )
            if need_update.rowcount != 1:
                db.rollback()
                raise HTTPException(409, "Need update conflicted; please retry.")
            db.flush()
            db.refresh(need)
            if need.quantity_fulfilled >= need.quantity_required:
                need.status = NEED_FULFILLED
                need_note = "Need automatically marked fulfilled."
                log_audit(
                    db,
                    actor_user_id=user.id,
                    action="need.fulfilled",
                    target_type="need",
                    target_id=need.id,
                    note=f"Need '{need.title}' fulfilled by donation {donation.reference}",
                )
        need_note = need_note or (
            f"Need fulfilled quantity += {delta:.4g} {need.unit}"
            + (" (capped at the remaining need)." if delta < quantity_received else "")
        )

    for recipient in {donation.donor_id, _org_owner(db, offer)}:
        notifications.notify(
            db,
            user_id=recipient,
            type="donation_completed",
            title=f"Donation completed: {donation.title}",
            body=f"{donation.reference} completed — {quantity_received:.4g} {donation.unit} received."
            + (f" {need_note}" if need_note else ""),
            link=f"/donations/{donation.id}",
        )
    log_audit(
        db,
        actor_user_id=user.id,
        action="offer.completed",
        target_type="offer",
        target_id=offer.id,
        note=f"Donation {donation.reference} completed ({quantity_received:.4g} {donation.unit} received)"
        + (f" | {need_note}" if need_note else ""),
        ip=getattr(request, "client", None) and request.client.host,
    )
    db.commit()
    db.refresh(offer)
    result = serialize_offer(db, offer)
    if need is not None:
        result["need"] = {
            "id": need.id,
            "quantity_fulfilled": need.quantity_fulfilled,
            "quantity_required": need.quantity_required,
            "remaining_quantity": need.remaining_quantity,
            "status": need.status,
        }
    return result
