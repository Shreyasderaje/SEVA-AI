"""Organization needs: CRUD, fulfilment tracking, status transitions, public
listing. Only VERIFIED organizations manage needs (§9)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    NEED_ACTIVE,
    NEED_CLOSED,
    NEED_FULFILLED,
    NEED_PAUSED,
    ROLE_ADMIN,
    ROLE_ORGANIZATION,
    VERIFICATION_VERIFIED,
)
from app.core.database import get_db
from app.core.deps import get_current_active_user, require_roles
from app.models.donation import DonationCategory, DonationSubcategory
from app.models.need import OrganizationNeed
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Page
from app.schemas.need import (
    NeedCreateRequest,
    NeedFulfilmentRequest,
    NeedOut,
    NeedStatusRequest,
    NeedUpdateRequest,
)
from app.services.audit import log_audit
from app.services.organization_access import get_own_organization

router = APIRouter(prefix="/api/needs", tags=["needs"])


def _serialize(db: Session, need: OrganizationNeed, *, include_org: bool = False) -> NeedOut:
    data = NeedOut.model_validate(need)
    data.is_demo = need.is_demo_data
    organization = db.get(Organization, need.organization_id) if include_org else None
    if include_org and organization is not None:
        data.is_demo = data.is_demo or organization.is_demo_data
    category = db.get(DonationCategory, need.category_id)
    data.category_code = category.code if category else None
    data.category_display_name = category.display_name if category else None
    if need.subcategory_id:
        subcategory = db.get(DonationSubcategory, need.subcategory_id)
        data.subcategory_display_name = subcategory.display_name if subcategory else None
    if include_org:
        data.organization_name = organization.name if organization else None
    return data


def _get_own_need(db: Session, user: User, need_id: str) -> OrganizationNeed:
    need = db.get(OrganizationNeed, need_id)
    if need is None:
        raise HTTPException(404, "Need not found")
    organization = get_own_organization(db, user)
    if need.organization_id != organization.id:
        raise HTTPException(404, "Need not found")  # no existence leak
    return need


def _validated_subcategory(db: Session, category_id: str, subcategory_id: str | None) -> str | None:
    if not subcategory_id:
        return None
    subcategory = db.get(DonationSubcategory, subcategory_id)
    if subcategory is None or not subcategory.is_active:
        raise HTTPException(422, "Unknown or inactive subcategory")
    if subcategory.category_id != category_id:
        raise HTTPException(422, "Subcategory does not belong to the selected category")
    return subcategory_id


@router.post("", response_model=NeedOut, status_code=status.HTTP_201_CREATED)
def create_need(
    payload: NeedCreateRequest,
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> NeedOut:
    organization = get_own_organization(db, user)
    if organization.verification_status != VERIFICATION_VERIFIED:
        raise HTTPException(
            403,
            f"Your organization is {organization.verification_status}. "
            "Only verified organizations can publish needs.",
        )
    category = db.get(DonationCategory, payload.category_id)
    if category is None or not category.is_active:
        raise HTTPException(422, "Unknown or inactive category")
    subcategory_id = _validated_subcategory(db, payload.category_id, payload.subcategory_id)

    need = OrganizationNeed(
        organization_id=organization.id,
        category_id=payload.category_id,
        subcategory_id=subcategory_id,
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        unit=payload.unit,
        quantity_required=payload.quantity_required,
        quantity_fulfilled=0.0,
        urgency=payload.urgency,
        required_by=payload.required_by,
        status=NEED_ACTIVE,
        notes=(payload.notes or "").strip() or None,
    )
    db.add(need)
    log_audit(
        db,
        actor_user_id=user.id,
        action="need.create",
        target_type="need",
        target_id=need.id,
        note=f"Need '{need.title}' created by {organization.name}",
    )
    db.commit()
    db.refresh(need)
    return _serialize(db, need)


@router.get("/mine", response_model=Page[NeedOut])
def my_needs(
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> Page[NeedOut]:
    organization = get_own_organization(db, user)
    query = select(OrganizationNeed).where(OrganizationNeed.organization_id == organization.id)
    count_query = (
        select(func.count())
        .select_from(OrganizationNeed)
        .where(OrganizationNeed.organization_id == organization.id)
    )
    if status_filter:
        query = query.where(OrganizationNeed.status == status_filter)
        count_query = count_query.where(OrganizationNeed.status == status_filter)
    total = db.scalar(count_query) or 0
    rows = db.scalars(
        query.order_by(OrganizationNeed.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[NeedOut](
        items=[_serialize(db, need) for need in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/public", response_model=list[NeedOut])
def public_needs(
    category_id: str | None = None,
    urgency: str | None = None,
    db: Session = Depends(get_db),
) -> list[NeedOut]:
    """Active needs of VERIFIED organizations — public, no auth (§6.3)."""
    query = (
        select(OrganizationNeed)
        .join(Organization, OrganizationNeed.organization_id == Organization.id)
        .where(
            OrganizationNeed.status == NEED_ACTIVE,
            Organization.verification_status == VERIFICATION_VERIFIED,
        )
    )
    if category_id:
        query = query.where(OrganizationNeed.category_id == category_id)
    if urgency:
        if urgency not in ("low", "medium", "high", "critical"):
            raise HTTPException(422, "Unknown urgency filter")
        query = query.where(OrganizationNeed.urgency == urgency)
    rows = db.scalars(query.order_by(OrganizationNeed.created_at.desc()).limit(100)).all()
    return [_serialize(db, need, include_org=True) for need in rows]


@router.get("/{need_id}", response_model=NeedOut)
def get_need(
    need_id: str,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> NeedOut:
    need = db.get(OrganizationNeed, need_id)
    if need is None:
        raise HTTPException(404, "Need not found")
    if user.role == ROLE_ADMIN:
        return _serialize(db, need, include_org=True)
    if user.role == ROLE_ORGANIZATION:
        organization = get_own_organization(db, user)
        if need.organization_id == organization.id:
            return _serialize(db, need)
    raise HTTPException(404, "Need not found")  # no existence leak


@router.patch("/{need_id}", response_model=NeedOut)
def update_need(
    need_id: str,
    payload: NeedUpdateRequest,
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> NeedOut:
    need = _get_own_need(db, user, need_id)
    organization = get_own_organization(db, user)
    if organization.verification_status != VERIFICATION_VERIFIED:
        raise HTTPException(403, "Only verified organizations can manage needs.")

    if payload.quantity_required is not None:
        # Fulfilled quantity can never exceed the new required quantity.
        if payload.quantity_required < need.quantity_fulfilled:
            raise HTTPException(
                422,
                f"Required quantity cannot be lower than the fulfilled quantity "
                f"({need.quantity_fulfilled:.4g}).",
            )
        need.quantity_required = payload.quantity_required
    if payload.title is not None:
        need.title = payload.title.strip()
    if payload.description is not None:
        need.description = payload.description.strip() or None
    if payload.urgency is not None:
        need.urgency = payload.urgency
    if payload.required_by is not None:
        need.required_by = payload.required_by
    if payload.notes is not None:
        need.notes = payload.notes.strip() or None
    if payload.subcategory_id is not None:
        need.subcategory_id = _validated_subcategory(db, need.category_id, payload.subcategory_id)

    if need.quantity_fulfilled >= need.quantity_required and need.status == NEED_ACTIVE:
        need.status = NEED_FULFILLED
    log_audit(
        db,
        actor_user_id=user.id,
        action="need.update",
        target_type="need",
        target_id=need.id,
        note=f"Need '{need.title}' updated",
    )
    db.commit()
    db.refresh(need)
    return _serialize(db, need)


@router.post("/{need_id}/status", response_model=NeedOut)
def change_need_status(
    need_id: str,
    payload: NeedStatusRequest,
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> NeedOut:
    need = _get_own_need(db, user, need_id)
    requested = payload.status
    allowed = {
        (NEED_ACTIVE, NEED_PAUSED),
        (NEED_PAUSED, NEED_ACTIVE),
        (NEED_ACTIVE, NEED_CLOSED),
        (NEED_PAUSED, NEED_CLOSED),
    }
    if (need.status, requested) not in allowed:
        raise HTTPException(
            409, f"Cannot change need status from {need.status} to {requested}"
        )
    need.status = requested
    log_audit(
        db,
        actor_user_id=user.id,
        action="need.status",
        target_type="need",
        target_id=need.id,
        note=f"Need '{need.title}' -> {requested}",
    )
    db.commit()
    db.refresh(need)
    return _serialize(db, need)


@router.post("/{need_id}/fulfilment", response_model=NeedOut)
def record_fulfilment(
    need_id: str,
    payload: NeedFulfilmentRequest,
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> NeedOut:
    """Record received quantity against a need (tracking only — the offer /
    completion workflows belong to M4).

    Race-safe: a conditional UPDATE guards against over-fulfilment even under
    concurrent requests; the check constraint is the second line of defence.
    """
    need = _get_own_need(db, user, need_id)
    if need.status not in (NEED_ACTIVE, NEED_PAUSED):
        raise HTTPException(409, f"Cannot record fulfilment on a {need.status} need")

    from sqlalchemy import update

    result = db.execute(
        update(OrganizationNeed)
        .where(
            OrganizationNeed.id == need.id,
            OrganizationNeed.quantity_fulfilled + payload.quantity
            <= OrganizationNeed.quantity_required,
        )
        .values(quantity_fulfilled=OrganizationNeed.quantity_fulfilled + payload.quantity)
    )
    if result.rowcount != 1:
        db.rollback()
        remaining = need.remaining_quantity
        raise HTTPException(
            422,
            f"Fulfilled quantity cannot exceed the required quantity "
            f"(remaining: {remaining:.4g} {need.unit}).",
        )
    db.flush()
    db.refresh(need)
    if need.quantity_fulfilled >= need.quantity_required and need.status == NEED_ACTIVE:
        need.status = NEED_FULFILLED
        log_audit(
            db,
            actor_user_id=user.id,
            action="need.fulfilled",
            target_type="need",
            target_id=need.id,
            note=f"Need '{need.title}' automatically marked fulfilled",
        )
    log_audit(
        db,
        actor_user_id=user.id,
        action="need.fulfilment",
        target_type="need",
        target_id=need.id,
        note=f"+{payload.quantity:.4g} {need.unit} recorded on '{need.title}'",
    )
    db.commit()
    db.refresh(need)
    return _serialize(db, need)
