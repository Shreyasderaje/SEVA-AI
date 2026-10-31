"""UPI payment setup, donor payment submission, and admin manual verification
(§9 — NO payment gateway; a submitted reference is never proof of payment)."""

import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    PAYMENT_REJECTED,
    PAYMENT_SUBMITTED,
    PAYMENT_VERIFIED,
    ROLE_ADMIN,
    ROLE_DONOR,
    ROLE_ORGANIZATION,
    UPI_STATUSES,
    VERIFICATION_VERIFIED,
)
from app.core.database import get_db
from app.core.deps import get_current_active_user, require_roles
from app.models.donation import Donation
from app.models.organization import Organization
from app.models.support import PaymentRecord
from app.models.user import User
from app.schemas.common import Page
from app.services import notifications
from app.services.audit import log_audit
from app.services.organization_access import get_own_organization
from app.services.storage import resolve_stored_path, storage_root

router = APIRouter(prefix="/api/payments", tags=["payments"])

UPI_ID_PATTERN = re.compile(r"^[a-zA-Z0-9.\-_]{2,64}@[a-zA-Z]{2,32}$")
TRANSACTION_REFERENCE_PATTERN = re.compile(r"^[a-zA-Z0-9]{6,40}$")

_MIME_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}


def _serialize_payment(payment: PaymentRecord) -> dict:
    return {
        "id": payment.id,
        "donation_id": payment.donation_id,
        "donor_id": payment.donor_id,
        "organization_id": payment.organization_id,
        "amount": payment.amount,
        "transaction_reference": payment.transaction_reference,
        "status": payment.status,
        "rejection_reason": payment.rejection_reason,
        "reviewed_by": payment.reviewed_by,
        "reviewed_at": payment.reviewed_at.isoformat() if payment.reviewed_at else None,
        "has_receipt": payment.receipt_path is not None,
        "receipt_url": f"/api/payments/{payment.id}/receipt" if payment.receipt_path else None,
        "created_at": payment.created_at.isoformat(),
    }


def _store_upload(data: bytes, subdir: str, mime: str) -> str:
    relative = Path(subdir) / f"{uuid.uuid4().hex}{_MIME_EXTENSIONS[mime]}"
    destination = storage_root() / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return relative.as_posix()


async def _read_validated_image(upload: UploadFile, *, max_bytes: int, label: str) -> tuple[bytes, str]:
    from app.services.storage import detect_document_mime

    data = await upload.read()
    if len(data) == 0:
        raise HTTPException(422, f"The uploaded {label} is empty")
    if len(data) > max_bytes:
        raise HTTPException(422, f"{label} must be {max_bytes // (1024 * 1024)} MB or smaller")
    mime = detect_document_mime(data)
    if mime is None:
        raise HTTPException(422, f"{label} must be a JPEG, PNG, or PDF file")
    return data, mime


# --------------------------------------------------- org UPI setup (M4 §9)


@router.post("/setup", status_code=201)
async def submit_upi_setup(
    request: Request,
    upi_id: str = Form(min_length=3, max_length=120),
    qr_image: UploadFile | None = File(default=None),
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> dict:
    organization = get_own_organization(db, user)
    if organization.verification_status != VERIFICATION_VERIFIED:
        raise HTTPException(403, "Only verified organizations can set up payments.")
    upi_id = upi_id.strip()
    if not UPI_ID_PATTERN.match(upi_id):
        raise HTTPException(422, "Enter a valid UPI ID (name@bank).")

    organization.upi_id = upi_id
    if qr_image is not None and (qr_image.filename or "").strip():
        data, mime = await _read_validated_image(qr_image, max_bytes=10 * 1024 * 1024, label="QR image")
        if mime not in ("image/jpeg", "image/png"):
            raise HTTPException(422, "QR image must be a JPEG or PNG image")
        organization.upi_qr_path = _store_upload(data, f"upi/{organization.id}", mime)
    organization.upi_status = "pending_approval"

    admins = db.scalars(select(User).where(User.role == ROLE_ADMIN)).all()
    for admin in admins:
        notifications.notify(
            db,
            user_id=admin.id,
            type="upi_setup_submitted",
            title=f"UPI setup submitted: {organization.name}",
            body="Review and approve the organization's payment details.",
            link="/admin/payments",
        )
    log_audit(
        db,
        actor_user_id=user.id,
        action="organization.upi_setup",
        target_type="organization",
        target_id=organization.id,
        note=f"UPI details submitted ({organization.upi_status})",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return {
        "upi_id": organization.upi_id,
        "upi_status": organization.upi_status,
        "has_qr": organization.upi_qr_path is not None,
    }


@router.get("/setup")
def my_upi_setup(
    user: User = Depends(require_roles(ROLE_ORGANIZATION)),
    db: Session = Depends(get_db),
) -> dict:
    organization = get_own_organization(db, user)
    return {
        "upi_id": organization.upi_id,
        "upi_status": organization.upi_status,
        "has_qr": organization.upi_qr_path is not None,
        "rejection_reason": (
            organization.rejection_reason if organization.upi_status == "rejected" else None
        ),
    }


@router.get("/upi/organizations/{organization_id}/qr")
def organization_qr(
    organization_id: str,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """QR image: visible to donors ONLY for verified + admin-approved orgs."""
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(404, "Organization not found")
    approved = (
        organization.verification_status == VERIFICATION_VERIFIED
        and organization.upi_status == "approved"
    )
    is_admin = user.role == ROLE_ADMIN
    is_owner = organization.owner_user_id == user.id
    if not approved and not (is_admin or is_owner):
        raise HTTPException(404, "Payment details are not available")
    if not organization.upi_qr_path:
        raise HTTPException(404, "No QR image on file")
    return FileResponse(resolve_stored_path(organization.upi_qr_path))


# -------------------------------------------------- donor payment submission


@router.post("", status_code=201)
async def submit_payment(
    request: Request,
    donation_id: str = Form(),
    organization_id: str = Form(),
    transaction_reference: str = Form(min_length=6, max_length=40),
    amount: float | None = Form(default=None, gt=0),
    receipt: UploadFile | None = File(default=None),
    user: User = Depends(require_roles(ROLE_DONOR)),
    db: Session = Depends(get_db),
) -> dict:
    donation = db.get(Donation, donation_id)
    if donation is None or donation.donor_id != user.id:
        raise HTTPException(404, "Donation not found")
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(404, "Organization not found")
    reference = transaction_reference.strip()
    if not TRANSACTION_REFERENCE_PATTERN.match(reference):
        raise HTTPException(422, "Transaction reference must be 6-40 letters/digits.")

    receipt_path = None
    if receipt is not None and (receipt.filename or "").strip():
        data, mime = await _read_validated_image(receipt, max_bytes=5 * 1024 * 1024, label="Receipt")
        receipt_path = _store_upload(data, f"payment_receipts/{user.id}", mime)

    payment = PaymentRecord(
        donor_id=user.id,
        organization_id=organization_id,
        donation_id=donation_id,
        transaction_reference=reference,
        amount=amount,
        receipt_path=receipt_path,
        status=PAYMENT_SUBMITTED,
    )
    db.add(payment)
    db.flush()
    log_audit(
        db,
        actor_user_id=user.id,
        action="payment.submitted",
        target_type="payment",
        target_id=payment.id,
        note=f"Reference {reference} for {organization.name} (pending verification)",
        ip=request.client.host if request.client else None,
    )
    admins = db.scalars(select(User).where(User.role == ROLE_ADMIN)).all()
    for admin in admins:
        notifications.notify(
            db,
            user_id=admin.id,
            type="payment_submitted",
            title="Payment reference submitted",
            body=f"Reference {reference} for {organization.name} — verify manually.",
            link="/admin/payments",
        )
    db.commit()
    db.refresh(payment)
    return _serialize_payment(payment)


@router.get("/mine")
def my_payments(
    user: User = Depends(require_roles(ROLE_DONOR)),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(
        select(PaymentRecord)
        .where(PaymentRecord.donor_id == user.id)
        .order_by(PaymentRecord.created_at.desc())
    ).all()
    return [_serialize_payment(p) for p in rows]


@router.get("/{payment_id}/receipt")
def payment_receipt(
    payment_id: str,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    payment = db.get(PaymentRecord, payment_id)
    if payment is None or payment.receipt_path is None:
        raise HTTPException(404, "Receipt not found")
    if user.role != ROLE_ADMIN and payment.donor_id != user.id:
        raise HTTPException(404, "Receipt not found")
    return FileResponse(resolve_stored_path(payment.receipt_path))


# ------------------------------------------------------------- admin review


@router.get("/upi/organizations")
def admin_upi_organizations(
    status_filter: str | None = Query(default=None, alias="status"),
    user: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(Organization).where(Organization.upi_id.isnot(None))
    if status_filter:
        if status_filter not in UPI_STATUSES:
            raise HTTPException(422, "Unknown UPI status filter")
        query = query.where(Organization.upi_status == status_filter)
    rows = db.scalars(query.order_by(Organization.name.asc())).all()
    return [
        {
            "id": org.id,
            "name": org.name,
            "verification_status": org.verification_status,
            "upi_id": org.upi_id,
            "upi_status": org.upi_status,
            "has_qr": org.upi_qr_path is not None,
        }
        for org in rows
    ]


@router.get("/admin/all", response_model=Page[dict])
def admin_payments(
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    user: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> Page[dict]:
    if status_filter and status_filter not in ("submitted_unverified", "verified", "rejected"):
        raise HTTPException(422, "Unknown status filter")
    query = select(PaymentRecord)
    count_query = select(func.count()).select_from(PaymentRecord)
    if status_filter:
        query = query.where(PaymentRecord.status == status_filter)
        count_query = count_query.where(PaymentRecord.status == status_filter)
    total = db.scalar(count_query) or 0
    rows = db.scalars(
        query.order_by(PaymentRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[dict](
        items=[_serialize_payment(p) for p in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


class PaymentDecision(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/admin/{payment_id}/verify")
def admin_verify_payment(
    payment_id: str,
    request: Request,
    user: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    return _decide_payment(db, request, user, payment_id, PAYMENT_VERIFIED, None)


@router.post("/admin/{payment_id}/reject")
def admin_reject_payment(
    payment_id: str,
    request: Request,
    payload: PaymentDecision,
    user: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    return _decide_payment(db, request, user, payment_id, PAYMENT_REJECTED, payload.reason)


def _decide_payment(
    db: Session,
    request: Request,
    user: User,
    payment_id: str,
    decision: str,
    reason: str | None,
) -> dict:
    payment = db.get(PaymentRecord, payment_id)
    if payment is None:
        raise HTTPException(404, "Payment not found")
    if payment.status != PAYMENT_SUBMITTED:
        raise HTTPException(409, f"This payment was already {payment.status}.")
    payment.status = decision
    payment.reviewed_by = user.id
    payment.reviewed_at = datetime.now()
    payment.rejection_reason = reason.strip() if decision == PAYMENT_REJECTED else None
    log_audit(
        db,
        actor_user_id=user.id,
        action=f"payment.{decision}",
        target_type="payment",
        target_id=payment.id,
        note=f"Reference {payment.transaction_reference} -> {decision}"
        + (f" | reason: {reason.strip()}" if reason and reason.strip() else ""),
        ip=request.client.host if request.client else None,
    )
    notifications.notify(
        db,
        user_id=payment.donor_id,
        type=f"payment_{decision}",
        title=f"Payment {decision}: {payment.transaction_reference}",
        body=reason.strip() if reason and reason.strip() else None,
    )
    db.commit()
    db.refresh(payment)
    return _serialize_payment(payment)
