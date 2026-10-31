"""Organization application, verification, documents, and public directory.

Authorization rules (§9):
- Only users with the organization role can apply; one application per user.
- Only admins change verification status (approve/reject/suspend), with a
  required reason for reject/suspend; every decision is audited.
- Application details and the verification document are visible only to the
  owning organization and admins — never through public URLs.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    ACCOUNT_ACTIVE,
    ROLE_ADMIN,
    ROLE_ORGANIZATION,
    VERIFICATION_PENDING,
    VERIFICATION_REJECTED,
    VERIFICATION_SUSPENDED,
    VERIFICATION_VERIFIED,
)
from app.core.database import get_db
from app.core.deps import get_current_active_user, require_roles
from app.models.need import OrganizationNeed
from app.models.organization import Organization, OrganizationDocument
from app.models.user import User
from app.schemas.common import Page
from app.schemas.organization import (
    AdminOrganizationOut,
    OrganizationApplicationOut,
    OrganizationListItem,
    OrganizationPublicOut,
    VerificationDecision,
    VerificationStatus,
)
from app.services.audit import log_audit
from app.services.organization_access import get_own_organization
from app.services.storage import resolve_stored_path, save_verification_document

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


def _get_own_organization(db: Session, user: User) -> Organization:
    return get_own_organization(db, user)


@router.post("/apply", response_model=OrganizationApplicationOut, status_code=status.HTTP_201_CREATED)
async def apply(
    request: Request,
    name: str = Form(min_length=3, max_length=200),
    org_type: str | None = Form(default=None, max_length=40),
    description: str | None = Form(default=None, max_length=1000),
    address: str | None = Form(default=None, max_length=500),
    contact_email: str | None = Form(default=None, max_length=255),
    contact_phone: str | None = Form(default=None, max_length=30),
    representative_name: str | None = Form(default=None, max_length=120),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    location_consent: bool = Form(default=False),
    document: UploadFile = File(...),
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> OrganizationApplicationOut:
    if user.status != ACCOUNT_ACTIVE:
        raise HTTPException(403, "Account is not active")
    existing = db.scalar(select(Organization).where(Organization.owner_user_id == user.id))
    if existing is not None:
        raise HTTPException(409, "An organization application already exists for this account")

    if (latitude is None) != (longitude is None):
        raise HTTPException(422, "Latitude and longitude must be provided together")
    if latitude is not None:
        if not location_consent:
            raise HTTPException(
                422, "Explicit consent is required to store organization coordinates"
            )
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):  # type: ignore[operator]
            raise HTTPException(422, "Coordinates out of range")

    organization = Organization(
        owner_user_id=user.id,
        name=name.strip(),
        org_type=(org_type or "").strip() or None,
        description=(description or "").strip() or None,
        address=(address or "").strip() or None,
        contact_email=(contact_email or "").strip() or None,
        contact_phone=(contact_phone or "").strip() or None,
        representative_name=(representative_name or "").strip() or None,
        latitude=latitude if location_consent else None,
        longitude=longitude if location_consent else None,
        verification_status=VERIFICATION_PENDING,
    )
    db.add(organization)
    db.flush()  # assigns organization.id for the storage layout

    # Validate + store the document under the real organization id. A 422 here
    # propagates before commit, so no partial rows or orphan files remain.
    stored = await save_verification_document(document, organization.id)
    db.add(
        OrganizationDocument(
            organization_id=organization.id,
            document_type="verification",
            stored_path=stored.stored_path,
        )
    )
    log_audit(
        db,
        actor_user_id=user.id,
        action="organization.apply",
        target_type="organization",
        target_id=organization.id,
        note=f"Application submitted for {organization.name}",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(organization)
    return OrganizationApplicationOut.model_validate(organization)


@router.get("/me", response_model=OrganizationApplicationOut)
def my_application(
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> OrganizationApplicationOut:
    return OrganizationApplicationOut.model_validate(_get_own_organization(db, user))


@router.get("/me/document")
def my_verification_document(
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> FileResponse:
    organization = _get_own_organization(db, user)
    document = db.scalar(
        select(OrganizationDocument).where(
            OrganizationDocument.organization_id == organization.id,
            OrganizationDocument.document_type == "verification",
        )
    )
    if document is None:
        raise HTTPException(404, "No verification document on file")
    return FileResponse(
        resolve_stored_path(document.stored_path), media_type=_document_mime(document)
    )


def _document_mime(document: OrganizationDocument) -> str:
    return {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".png": "image/png",
    }.get(document.stored_path[-4:].lower(), "application/octet-stream")


@router.get("", response_model=list[OrganizationPublicOut])
def public_directory(db: Session = Depends(get_db)) -> list[OrganizationPublicOut]:
    """Public list of VERIFIED organizations (§5.1) — no contact details."""
    organizations = db.scalars(
        select(Organization)
        .where(Organization.verification_status == VERIFICATION_VERIFIED)
        .order_by(Organization.name.asc())
    ).all()
    return [OrganizationPublicOut.model_validate(org) for org in organizations]


@router.get("/{organization_id}/public-needs")
def public_needs(
    organization_id: str,
    db: Session = Depends(get_db),
) -> list[dict]:
    """Public active needs of a VERIFIED organization (§6.3)."""
    organization = db.get(Organization, organization_id)
    if (
        organization is None
        or organization.verification_status != VERIFICATION_VERIFIED
    ):
        raise HTTPException(404, "Organization not found")
    needs = db.scalars(
        select(OrganizationNeed).where(
            OrganizationNeed.organization_id == organization_id,
            OrganizationNeed.status == "active",
        )
    ).all()
    return [
        {
            "id": need.id,
            "title": need.title,
            "category_id": need.category_id,
            "unit": need.unit,
            "quantity_required": need.quantity_required,
            "quantity_fulfilled": need.quantity_fulfilled,
            "remaining_quantity": need.remaining_quantity,
            "urgency": need.urgency,
            "required_by": need.required_by.isoformat() if need.required_by else None,
        }
        for need in needs
    ]


# --------------------------------------------------------------------- admin


@router.get("/admin/all", response_model=Page[OrganizationListItem])
def admin_list_organizations(
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    user: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> Page[OrganizationListItem]:
    if status_filter and status_filter not in VerificationStatus.__args__:
        raise HTTPException(422, "Unknown verification status filter")
    query = select(Organization)
    count_query = select(func.count()).select_from(Organization)
    if status_filter:
        query = query.where(Organization.verification_status == status_filter)
        count_query = count_query.where(Organization.verification_status == status_filter)
    total = db.scalar(count_query) or 0
    rows = db.scalars(
        query.order_by(Organization.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[OrganizationListItem](
        items=[OrganizationListItem.model_validate(org) for org in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/admin/{organization_id}", response_model=AdminOrganizationOut)
def admin_organization_detail(
    organization_id: str,
    user: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> AdminOrganizationOut:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(404, "Organization not found")
    document = db.scalar(
        select(OrganizationDocument).where(
            OrganizationDocument.organization_id == organization.id,
            OrganizationDocument.document_type == "verification",
        )
    )
    data = AdminOrganizationOut.model_validate(organization)
    if document is not None:
        data.document_id = document.id
        data.document_url = f"/api/organizations/{organization.id}/verification-document"
    return data


@router.get("/{organization_id}/verification-document")
def verification_document(
    organization_id: str,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Verification document: owning organization or admin ONLY (§9)."""
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(404, "Organization not found")
    if user.role != ROLE_ADMIN and organization.owner_user_id != user.id:
        raise HTTPException(404, "Organization not found")  # no existence leak
    document = db.scalar(
        select(OrganizationDocument).where(
            OrganizationDocument.organization_id == organization.id,
            OrganizationDocument.document_type == "verification",
        )
    )
    if document is None:
        raise HTTPException(404, "No verification document on file")
    return FileResponse(
        resolve_stored_path(document.stored_path), media_type=_document_mime(document)
    )


def _decide(
    db: Session,
    request: Request,
    user: User,
    organization_id: str,
    decision: VerificationStatus,
    reason: str | None,
) -> Organization:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(404, "Organization not found")
    if decision in (VERIFICATION_REJECTED, VERIFICATION_SUSPENDED) and not (reason and reason.strip()):
        raise HTTPException(422, "A reason is required for rejection or suspension")

    previous = organization.verification_status
    organization.verification_status = decision
    organization.rejection_reason = (
        reason.strip() if decision in (VERIFICATION_REJECTED, VERIFICATION_SUSPENDED) else None
    )
    from datetime import datetime

    organization.verified_at = (
        datetime.now() if decision == VERIFICATION_VERIFIED else None
    )
    log_audit(
        db,
        actor_user_id=user.id,
        action=f"organization.{decision}",
        target_type="organization",
        target_id=organization.id,
        note=f"{organization.name}: {previous} -> {decision}"
        + (f" | reason: {reason.strip()}" if reason and reason.strip() else ""),
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(organization)
    return organization


@router.post("/admin/{organization_id}/verify", response_model=AdminOrganizationOut)
def admin_verify(
    organization_id: str,
    request: Request,
    user: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> AdminOrganizationOut:
    organization = _decide(db, request, user, organization_id, VERIFICATION_VERIFIED, None)
    return AdminOrganizationOut.model_validate(organization)


@router.post("/admin/{organization_id}/reject", response_model=AdminOrganizationOut)
def admin_reject(
    organization_id: str,
    request: Request,
    payload: VerificationDecision,
    user: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> AdminOrganizationOut:
    organization = _decide(
        db, request, user, organization_id, VERIFICATION_REJECTED, payload.reason
    )
    return AdminOrganizationOut.model_validate(organization)


@router.post("/admin/{organization_id}/suspend", response_model=AdminOrganizationOut)
def admin_suspend(
    organization_id: str,
    request: Request,
    payload: VerificationDecision,
    user: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> AdminOrganizationOut:
    organization = _decide(
        db, request, user, organization_id, VERIFICATION_SUSPENDED, payload.reason
    )
    return AdminOrganizationOut.model_validate(organization)
