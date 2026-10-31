"""Sequential offer workflow (M4 §5) — the heart of the milestone.

Rules implemented here (master §6.4, addendum §1/§9, M4 authorization §5/§6):

- ONE active offer per donation at any time.
- Candidates come from the M3 matching engine (never duplicated here); the
  offer layer skips organizations that already have ANY offer for this
  donation (declined/accepted/withdrawn) — a decliner is never re-offered.
- Initiation is guarded by a conditional donation status update
  (pending → offered): repeated API calls cannot create duplicate offers.
- Accept is atomic: conditional updates on BOTH the offer (sent → accepted)
  and the donation (offered → accepted); a decline racing an accept cannot
  produce two terminal offers because both guard on status='sent'.
- Decline marks ONLY the offer; the donation stays `offered` while the next
  candidate is selected; when no candidate remains the donation returns to
  `pending` and the donor is notified.
- Matching score, factors, weights, distance, and reasons are snapshotted at
  offer creation and never recomputed.
"""

import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.constants import (
    DONATION_ACCEPTED,
    DONATION_OFFERED,
    DONATION_PENDING,
    OFFER_ACCEPTED,
    OFFER_DECLINED,
    OFFER_SENT,
)
from app.models.donation import Donation
from app.models.offer import DonationOffer
from app.models.organization import Organization
from app.models.user import User
from app.services import notifications
from app.services.audit import log_audit
from app.services.matching import compute_matches


def _org_id_for_user(db: Session, user: User) -> str:
    organization = db.scalar(
        select(Organization).where(Organization.owner_user_id == user.id)
    )
    if organization is None:
        raise HTTPException(404, "No organization application found.")
    return organization.id


def serialize_offer(db: Session, offer: DonationOffer, *, include_org: bool = False) -> dict:
    organization = db.get(Organization, offer.organization_id)
    factor_snapshot = json.loads(offer.factor_json) if offer.factor_json else None
    data = {
        "id": offer.id,
        "donation_id": offer.donation_id,
        "organization_id": offer.organization_id,
        "organization_name": organization.name if organization else None,
        "status": offer.status,
        "score": offer.score,
        "rank_at_offer": offer.rank_at_offer,
        "factor_snapshot": factor_snapshot,
        "reason_text": offer.reason_text,
        "decline_reason": offer.decline_reason,
        "quantity_received": offer.quantity_received,
        "pickup_date": offer.pickup_date.isoformat() if offer.pickup_date else None,
        "pickup_window_start": (
            offer.pickup_window_start.isoformat() if offer.pickup_window_start else None
        ),
        "pickup_window_end": (
            offer.pickup_window_end.isoformat() if offer.pickup_window_end else None
        ),
        "pickup_instructions": offer.pickup_instructions,
        "responded_at": offer.responded_at.isoformat() if offer.responded_at else None,
        "created_at": offer.created_at.isoformat(),
    }
    if include_org:
        donation = db.get(Donation, offer.donation_id)
        data["donation_title"] = donation.title if donation else None
        data["donation_reference"] = donation.reference if donation else None
        data["donation_quantity"] = donation.quantity if donation else None
        data["donation_unit"] = donation.unit if donation else None
    return data


def initiate_offer(db: Session, donation: Donation, actor: User, request=None) -> dict:
    """Create the next offer for a donation (donor-initiated or after decline).

    Returns a summary dict; never fabricates a recipient when no candidate
    exists (donation returns to pending + donor notified).
    """
    if donation.status not in (DONATION_PENDING, DONATION_OFFERED):
        raise HTTPException(
            409, f"Offers can only be initiated from pending or offered donations "
            f"(current: {donation.status})"
        )

    # One active offer per donation: a repeated initiation while an offer is
    # still `sent` is a no-op, never a withdrawal or a second offer.
    active_offer = db.scalar(
        select(DonationOffer).where(
            DonationOffer.donation_id == donation.id,
            DonationOffer.status == OFFER_SENT,
        )
    )
    if active_offer is not None:
        db.rollback()
        return {
            "donation_id": donation.id,
            "status": donation.status,
            "offer": serialize_offer(db, active_offer),
            "message": "An offer is already active for this donation.",
        }

    result = compute_matches(db, donation)
    offered_org_ids = {
        org_id
        for (org_id,) in db.execute(
            select(DonationOffer.organization_id).where(
                DonationOffer.donation_id == donation.id
            )
        ).all()
    }
    candidate = next(
        (c for c in result["eligible"] if c["organization_id"] not in offered_org_ids),
        None,
    )

    if candidate is None:
        if donation.status == DONATION_OFFERED:
            # Withdraw any lingering active offer (defensive; decline already
            # terminalizes it) and return the donation to pending.
            db.execute(
                update(DonationOffer)
                .where(
                    DonationOffer.donation_id == donation.id,
                    DonationOffer.status == OFFER_SENT,
                )
                .values(status="withdrawn")
            )
            record_transition(
                db, donation, to_status=DONATION_PENDING, actor_user_id=actor.id,
                note="No eligible organization available",
            )
        # The donor is always told when no organization is available (§5).
        notify_donor_no_candidate(db, donation)
        db.commit()
        return {
            "donation_id": donation.id,
            "status": donation.status,
            "offer": None,
            "message": "No eligible organization is currently available.",
        }

    # Guard the donation transition (pending -> offered) so repeated calls
    # cannot create two active offers. The history row is written FIRST: the
    # bulk UPDATE below synchronizes the in-memory status, and record_transition
    # would otherwise see 'offered' and skip the append-only history entry.
    if donation.status == DONATION_PENDING:
        record_transition(
            db, donation, to_status=DONATION_OFFERED, actor_user_id=actor.id,
            note=f"Offer sent to {candidate['organization_name']}",
        )
        guarded = db.execute(
            update(Donation)
            .where(Donation.id == donation.id, Donation.status == DONATION_PENDING)
            .values(status=DONATION_OFFERED)
        )
        if guarded.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Donation is no longer available for offers")
    db.refresh(donation)

    offer = DonationOffer(
        donation_id=donation.id,
        organization_id=candidate["organization_id"],
        need_id=candidate["need_id"],
        status=OFFER_SENT,
        score=candidate["score"],
        rank_at_offer=candidate["rank"],
        factor_json=json.dumps(
            {
                "factors": candidate["factors"],
                "reasons": candidate["reasons"],
                "service_radius_km": result["service_radius_km"],
                "distance_km": candidate["distance_km"],
            },
            default=str,
        ),
        reason_text="; ".join(candidate["reasons"]),
    )
    db.add(offer)
    db.flush()

    notifications.notify(
        db,
        user_id=_owner_user_id(db, candidate["organization_id"]),
        type="offer_received",
        title=f"New donation offer: {donation.title}",
        body=f"{donation.quantity:.4g} {donation.unit} — match score {candidate['score']:.1f}.",
        link=f"/organization/offers",
    )
    notifications.notify(
        db,
        user_id=donation.donor_id,
        type="offer_sent",
        title=f"Offer sent to {candidate['organization_name']}",
        body=f"Your donation {donation.reference} was offered to the top-ranked organization.",
        link=f"/donations/{donation.id}",
    )
    log_audit(
        db,
        actor_user_id=actor.id,
        action="offer.sent",
        target_type="offer",
        target_id=offer.id,
        note=f"Donation {donation.reference} offered to {candidate['organization_name']} "
        f"(score {candidate['score']:.1f})",
        ip=getattr(request, "client", None) and request.client.host,
    )
    db.commit()
    db.refresh(offer)
    return {
        "donation_id": donation.id,
        "status": donation.status,
        "offer": serialize_offer(db, offer),
        "message": f"Offer sent to {candidate['organization_name']}.",
    }


def record_transition(
    db: Session,
    donation: Donation,
    *,
    to_status: str,
    actor_user_id: str | None,
    note: str | None = None,
) -> bool:
    """Append history + move the donation's overall status (dedupe-aware, §1)."""
    from app.models.offer import DonationStatusHistory

    if donation.status == to_status:
        return False
    next_seq = db.scalar(
        select(func.coalesce(func.max(DonationStatusHistory.seq), 0)).where(
            DonationStatusHistory.donation_id == donation.id
        )
    ) or 0
    db.add(
        DonationStatusHistory(
            donation_id=donation.id,
            actor_user_id=actor_user_id,
            from_status=donation.status,
            to_status=to_status,
            note=note[:500] if note else None,
            seq=next_seq + 1,
        )
    )
    donation.status = to_status
    return True


def _owner_user_id(db: Session, organization_id: str) -> str:
    organization = db.get(Organization, organization_id)
    return organization.owner_user_id if organization else ""


def get_own_offer(db: Session, user: User, offer_id: str) -> DonationOffer:
    offer = db.get(DonationOffer, offer_id)
    if offer is None:
        raise HTTPException(404, "Offer not found")
    if user.role == "admin" or user.role == "donor":
        donation = db.get(Donation, offer.donation_id)
        if user.role == "donor" and (donation is None or donation.donor_id != user.id):
            raise HTTPException(404, "Offer not found")
        return offer
    if user.role == "organization":
        organization = db.scalar(
            select(Organization).where(Organization.owner_user_id == user.id)
        )
        if organization is None or offer.organization_id != organization.id:
            raise HTTPException(404, "Offer not found")
        return offer
    raise HTTPException(404, "Offer not found")


def accept_offer(db: Session, offer: DonationOffer, user: User, request=None) -> dict:
    organization_id = _org_id_for_user(db, user)
    if offer.organization_id != organization_id:
        raise HTTPException(403, "This offer is addressed to another organization")
    donation = db.get(Donation, offer.donation_id)
    if donation is None:
        raise HTTPException(404, "Donation not found")

    # Atomic accept: BOTH conditional updates must succeed in one transaction.
    # The history row is written FIRST — the bulk donation update below
    # synchronizes the in-memory status, and record_transition's dedupe guard
    # would otherwise skip the append-only history entry.
    record_transition(
        db, donation, to_status=DONATION_ACCEPTED,
        actor_user_id=user.id, note=f"Accepted by {_org_name(db, offer)}",
    )
    offer_update = db.execute(
        update(DonationOffer)
        .where(DonationOffer.id == offer.id, DonationOffer.status == OFFER_SENT)
        .values(status=OFFER_ACCEPTED, responded_at=datetime.now())
    )
    donation_update = db.execute(
        update(Donation)
        .where(Donation.id == donation.id, Donation.status == DONATION_OFFERED)
        .values(status=DONATION_ACCEPTED)
    )
    if offer_update.rowcount != 1 or donation_update.rowcount != 1:
        db.rollback()
        raise HTTPException(
            409,
            "This offer is no longer available "
            "(already accepted, declined, or the donation is not in the offered state).",
        )
    notifications.notify(
        db,
        user_id=donation.donor_id,
        type="offer_accepted",
        title=f"Donation accepted: {donation.title}",
        body=f"{_org_name(db, offer)} accepted your donation {donation.reference}.",
        link=f"/donations/{donation.id}",
    )
    notifications.notify(
        db,
        user_id=_owner_user_id(db, organization_id),
        type="offer_accepted_org",
        title=f"You accepted: {donation.title}",
        body="Schedule the pickup from your organization dashboard.",
        link="/organization/offers",
    )
    log_audit(
        db,
        actor_user_id=user.id,
        action="offer.accepted",
        target_type="offer",
        target_id=offer.id,
        note=f"Donation {donation.reference} accepted by {_org_name(db, offer)}",
        ip=getattr(request, "client", None) and request.client.host,
    )
    db.commit()
    db.refresh(offer)
    return serialize_offer(db, offer)


def _org_name(db: Session, offer: DonationOffer) -> str:
    organization = db.get(Organization, offer.organization_id)
    return organization.name if organization else "the organization"


def decline_offer(
    db: Session, offer: DonationOffer, user: User, reason: str | None, request=None
) -> dict:
    organization_id = _org_id_for_user(db, user)
    if offer.organization_id != organization_id:
        raise HTTPException(403, "This offer is addressed to another organization")
    donation = db.get(Donation, offer.donation_id)
    if donation is None:
        raise HTTPException(404, "Donation not found")

    decline_update = db.execute(
        update(DonationOffer)
        .where(DonationOffer.id == offer.id, DonationOffer.status == OFFER_SENT)
        .values(
            status=OFFER_DECLINED,
            decline_reason=(reason or "").strip() or None,
            responded_at=datetime.now(),
        )
    )
    if decline_update.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "This offer is no longer active (already accepted or declined).")

    notifications.notify(
        db,
        user_id=donation.donor_id,
        type="offer_declined",
        title=f"Offer declined: {donation.title}",
        body=f"{_org_name(db, offer)} declined your donation {donation.reference}."
        + (f" Reason: {reason.strip()}" if reason and reason.strip() else ""),
        link=f"/donations/{donation.id}",
    )
    log_audit(
        db,
        actor_user_id=user.id,
        action="offer.declined",
        target_type="offer",
        target_id=offer.id,
        note=f"Donation {donation.reference} declined"
        + (f" | reason: {reason.strip()}" if reason and reason.strip() else ""),
        ip=getattr(request, "client", None) and request.client.host,
    )
    db.flush()

    # Select the next candidate (donation stays `offered` while selecting).
    outcome = initiate_offer(db, donation, user, request=request)
    db.commit()
    db.refresh(offer)
    return {
        "offer": serialize_offer(db, offer),
        "next": outcome,
    }


def notify_donor_no_candidate(db: Session, donation: Donation) -> None:
    notifications.notify(
        db,
        user_id=donation.donor_id,
        type="no_candidate",
        title=f"No organization available: {donation.title}",
        body=f"No eligible organization is currently available for {donation.reference}. "
        "The donation is pending and can be offered again later.",
        link=f"/donations/{donation.id}",
    )
