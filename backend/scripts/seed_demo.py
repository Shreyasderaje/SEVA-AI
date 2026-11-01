"""Demo seed script (M5 §4) — development ONLY.

Creates clearly-labelled demonstration records with `is_demo_data=True`:
donors, organizations (verified + pending), needs, donations with generated
placeholder photos, sequential offers, notifications, and payment records.

Safety:
- Refuses to run unless SEVA_ENV=development.
- Idempotent: stable demo emails/names — re-running fills gaps without
  duplicating.
- Preserves every non-demo record; the admin account is untouched.

Usage (from backend/):
    set SEVA_ENV=development  (PowerShell: $env:SEVA_ENV="development")
    .venv/Scripts/python.exe scripts/seed_demo.py
"""

import io
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.constants import ROLE_ADMIN  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.donation import (  # noqa: E402
    Donation,
    DonationCategory,
    DonationImage,
)
from app.models.need import OrganizationNeed  # noqa: E402
from app.models.offer import DonationOffer, DonationStatusHistory  # noqa: E402
from app.models.organization import Organization, OrganizationDocument  # noqa: E402
from app.models.support import Notification, PaymentRecord  # noqa: E402
from app.models.user import DonorProfile, User  # noqa: E402
from app.services.storage import storage_root  # noqa: E402

DEMO_DOMAIN = "demo.seva"
DEMO_PASSWORD = "DemoOnlyPass1"  # development-only; printed, never valid in prod


def _require_development() -> None:
    env = os.environ.get("SEVA_ENV", "").strip().lower()
    print(f"environment: SEVA_ENV={env or '(unspecified)'} | operation: seed demo data")
    if env != "development":
        sys.exit(
            "refusing to run: demo seeding is allowed only with SEVA_ENV=development."
        )


def _jpg(color: tuple[int, int, int]) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=color).save(buffer, "JPEG")
    return buffer.getvalue()


def _get_user(db, email: str) -> User:
    return db.scalar(select(User).where(User.email == email))


def _ensure_user(db, email, name, role) -> User:
    user = _get_user(db, email)
    if user is not None:
        return user
    user = User(
        email=email,
        password_hash=hash_password(DEMO_PASSWORD),
        full_name=name,
        role=role,
        is_demo_data=True,
    )
    db.add(user)
    db.flush()
    if role == "donor":
        db.add(DonorProfile(user_id=user.id, is_demo_data=True))
    print(f"  user: {name} <{email}> ({role})")
    return user


def _ensure_organization(db, user: User, name: str, org_type: str, verified: bool,
                         latitude: float | None, longitude: float | None) -> Organization:
    organization = db.scalar(
        select(Organization).where(Organization.owner_user_id == user.id)
    )
    if organization is not None:
        return organization
    organization = Organization(
        owner_user_id=user.id,
        name=name,
        org_type=org_type,
        description=f"Demo {org_type} for demonstration purposes (not a real charity).",
        address="Demo address, Springfield",
        latitude=latitude,
        longitude=longitude,
        contact_email=user.email,
        representative_name=f"Demo representative ({name})",
        verification_status="verified" if verified else "pending_verification",
        verified_at=datetime.now() if verified else None,
        is_demo_data=True,
    )
    db.add(organization)
    db.flush()
    doc_path = Path(storage_root() / "verification" / organization.id / "demo.pdf")
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_bytes(b"%PDF-1.4 demo verification document (generated)")
    db.add(
        OrganizationDocument(
            organization_id=organization.id,
            document_type="verification",
            stored_path=doc_path.relative_to(storage_root()).as_posix(),
            is_demo_data=True,
        )
    )
    print(f"  organization: {name} ({'verified' if verified else 'pending'})")
    return organization


def _ensure_need(db, organization: Organization, category: DonationCategory,
                 title: str, required: float, urgency: str) -> OrganizationNeed:
    existing = db.scalar(
        select(OrganizationNeed).where(
            OrganizationNeed.organization_id == organization.id,
            OrganizationNeed.title == title,
        )
    )
    if existing is not None:
        return existing
    need = OrganizationNeed(
        organization_id=organization.id,
        category_id=category.id,
        title=title,
        description=f"Demo need — {title}.",
        unit="pieces",
        quantity_required=required,
        quantity_fulfilled=0.0,
        urgency=urgency,
        required_by=date.today() + timedelta(days=20),
        status="active",
        is_demo_data=True,
    )
    db.add(need)
    db.flush()
    print(f"  need: {title} ({organization.name})")
    return need


def _ensure_donation(db, donor: User, category: DonationCategory, title: str,
                     reference: str, status: str, color) -> Donation | None:
    existing = db.scalar(select(Donation).where(Donation.reference == reference))
    if existing is not None:
        return existing
    donation = Donation(
        reference=reference,
        donor_id=donor.id,
        category_id=category.id,
        title=title,
        description=f"Demo donation — {title}.",
        quantity=10,
        unit="pieces",
        condition="good",
        pickup_area="Demo pickup area",
        status=status,
        is_demo_data=True,
    )
    db.add(donation)
    db.flush()
    image = storage_root() / "donations" / donation.id / "demo-photo.jpg"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(_jpg(color))
    db.add(
        DonationImage(
            donation_id=donation.id,
            stored_path=image.relative_to(storage_root()).as_posix(),
            mime_type="image/jpeg",
            size_bytes=image.stat().st_size,
            position=1,
            is_demo_data=True,
        )
    )
    db.add(
        DonationStatusHistory(
            donation_id=donation.id,
            actor_user_id=donor.id,
            from_status=None,
            to_status="pending",
            note="Demo donation created",
            seq=1,
            is_demo_data=True,
        )
    )
    print(f"  donation: {reference} ({status}) — {title}")
    return donation


def main() -> int:
    _require_development()
    db = SessionLocal()
    created = {"offers": 0, "notifications": 0, "payments": 0}
    try:
        print("seeding demo data (idempotent)…")

        # ---- accounts ------------------------------------------------------
        admin = db.scalar(select(User).where(User.role == ROLE_ADMIN))
        donors = [
            _ensure_user(db, f"demo.donor.{i:02d}@{DEMO_DOMAIN}", f"Demo Donor {i:02d}", "donor")
            for i in (1, 2, 3)
        ]
        org_a_user = _ensure_user(db, f"demo.org.clothing@{DEMO_DOMAIN}", "Demo Clothing Support Organization", "organization")
        org_b_user = _ensure_user(db, f"demo.org.food@{DEMO_DOMAIN}", "Demo Food Relief Organization", "organization")
        org_pending_user = _ensure_user(db, f"demo.org.pending@{DEMO_DOMAIN}", "Demo Pending Organization", "organization")

        # ---- organizations ---------------------------------------------------
        org_a = _ensure_organization(db, org_a_user, "Demo Clothing Support Organization",
                                     "ngo", verified=True, latitude=12.9716, longitude=77.5946)
        org_b = _ensure_organization(db, org_b_user, "Demo Food Relief Organization",
                                     "ngo", verified=True, latitude=13.0500, longitude=77.6000)
        _ensure_organization(db, org_pending_user, "Demo Pending Organization",
                             "trust", verified=False, latitude=None, longitude=None)

        # ---- needs -----------------------------------------------------------
        categories = {c.code: c for c in db.scalars(select(DonationCategory)).all()}
        need_a = _ensure_need(db, org_a, categories["clothing"], "Winter clothes for families", 25, "critical")
        need_b = _ensure_need(db, org_b, categories["packaged_food"], "Packaged food parcels", 40, "high")

        # ---- donations ---------------------------------------------------------
        donations = [
            _ensure_donation(db, donors[0], categories["clothing"],
                             "Demo winter jackets", "SEVA-DEMO-000001", "pending", (60, 90, 160)),
            _ensure_donation(db, donors[1], categories["packaged_food"],
                             "Demo canned food boxes", "SEVA-DEMO-000002", "pending", (150, 110, 60)),
            _ensure_donation(db, donors[2], categories["clothing"],
                             "Demo completed clothing bundle", "SEVA-DEMO-000003", "completed", (90, 60, 140)),
        ]

        # ---- sequential offers (demo: one declined, one accepted) -------------
        def _ensure_offer(db, donation: Donation, organization: Organization, status: str, note: str | None = None):
            existing = db.scalar(
                select(DonationOffer).where(
                    DonationOffer.donation_id == donation.id,
                    DonationOffer.organization_id == organization.id,
                )
            )
            if existing is not None:
                return existing
            offer = DonationOffer(
                donation_id=donation.id,
                organization_id=organization.id,
                need_id=need_a.id if need_a.category_id == donation.category_id else need_b.id,
                status=status,
                score=78.5,
                rank_at_offer=1,
                factor_json='{"factors": {"compatibility": {"score": 1.0, "weight": 0.3, "weighted": 0.3}, '
                            '"urgency": {"score": 0.75, "weight": 0.25, "weighted": 0.1875}, '
                            '"distance": {"score": 0.5, "weight": 0.2, "weighted": 0.1}, '
                            '"quantity_fit": {"score": 0.5, "weight": 0.15, "weighted": 0.075}, '
                            '"timeliness": {"score": 0.5, "weight": 0.1, "weighted": 0.05}}, '
                            '"reasons": ["Demo matching snapshot."], "distance_km": null, '
                            '"service_radius_km": 50}',
                reason_text="Demo matching snapshot — factors recorded at offer time.",
                decline_reason=note if status == "declined" else None,
                responded_at=datetime.now() if status != "sent" else None,
                is_demo_data=True,
            )
            db.add(offer)
            db.flush()
            created["offers"] += 1
            print(f"  offer: {donation.reference} -> {organization.name} ({status})")
            if status == "accepted":
                offer.quantity_received = 9
                donation.status = "accepted"
                db.add(
                    DonationStatusHistory(
                        donation_id=donation.id, actor_user_id=None,
                        from_status="offered", to_status="accepted",
                        note="Demo offer accepted", seq=2, is_demo_data=True,
                    )
                )
            return offer

        demo_completed = donations[2]
        demo_completed.status = "completed"
        demo_completed_pickup_offer = _ensure_offer(
            db, demo_completed, org_a, "accepted"
        )
        demo_completed_pickup_offer.pickup_date = date.today() + timedelta(days=1)
        demo_completed_pickup_offer.pickup_window_start = datetime.now().replace(hour=10, minute=0)
        demo_completed_pickup_offer.pickup_window_end = datetime.now().replace(hour=12, minute=0)
        demo_completed_pickup_offer.pickup_instructions = "Demo pickup instructions."
        demo_completed_pickup_offer.quantity_received = 9
        db.add(
            DonationStatusHistory(
                donation_id=demo_completed.id, actor_user_id=None,
                from_status="offered", to_status="accepted",
                note="Demo offer accepted", seq=2, is_demo_data=True,
            )
        )
        db.add(
            DonationStatusHistory(
                donation_id=demo_completed.id, actor_user_id=None,
                from_status="accepted", to_status="pickup_scheduled",
                note="Demo pickup scheduled", seq=3, is_demo_data=True,
            )
        )
        db.add(
            DonationStatusHistory(
                donation_id=demo_completed.id, actor_user_id=None,
                from_status="pickup_scheduled", to_status="picked_up",
                note="Demo pickup", seq=4, is_demo_data=True,
            )
        )
        db.add(
            DonationStatusHistory(
                donation_id=demo_completed.id, actor_user_id=None,
                from_status="picked_up", to_status="completed",
                note="Demo completion — 9 of 10 pieces received", seq=5, is_demo_data=True,
            )
        )

        pending_donation = donations[0]
        _ensure_offer(db, pending_donation, org_a, "declined", "Demo decline reason")
        _ensure_offer(db, pending_donation, org_b, "sent")

        # ---- notifications (demo) --------------------------------------------
        def _ensure_notification(user: User, type_: str, title: str):
            existing = db.scalar(
                select(Notification).where(
                    Notification.user_id == user.id, Notification.title == title
                )
            )
            if existing is None:
                db.add(
                    Notification(user_id=user.id, type=type_, title=title,
                                 body="Demo notification.", is_demo_data=True)
                )
                created["notifications"] += 1
                print(f"  notification: {title} -> {user.email}")

        _ensure_notification(org_a_user, "offer_declined", "Demo: offer declined")
        _ensure_notification(donors[0], "no_candidate", "Demo: no candidate available")
        if admin:
            _ensure_notification(admin, "payment_submitted", "Demo: payment awaiting verification")

        # ---- payment records (demo) -------------------------------------------
        if admin:
            demo_payment = db.scalar(
                select(PaymentRecord).where(
                    PaymentRecord.transaction_reference == "DEMOPAY0001"
                )
            )
            if demo_payment is None:
                db.add(
                    PaymentRecord(
                        donor_id=donors[1].id,
                        organization_id=org_b.id,
                        donation_id=donations[1].id,
                        transaction_reference="DEMOPAY0001",
                        amount=500.0,
                        status="submitted_unverified",
                        is_demo_data=True,
                    )
                )
                created["payments"] += 1
                print("  payment: DEMOPAY0001 (submitted_unverified)")
            verified_payment = db.scalar(
                select(PaymentRecord).where(
                    PaymentRecord.transaction_reference == "DEMOPAY0002"
                )
            )
            if verified_payment is None:
                db.add(
                    PaymentRecord(
                        donor_id=donors[0].id,
                        organization_id=org_a.id,
                        donation_id=donations[2].id,
                        transaction_reference="DEMOPAY0002",
                        amount=750.0,
                        status="verified",
                        reviewed_by=admin.id,
                        reviewed_at=datetime.now(),
                        is_demo_data=True,
                    )
                )
                created["payments"] += 1
                print("  payment: DEMOPAY0002 (verified)")

        db.commit()
        print()
        print(f"demo seed complete. new records this run: {created}")
        print(f"demo accounts use password: {DEMO_PASSWORD} (development-only)")
        print("demo emails end with @" + DEMO_DOMAIN + " — every record is flagged is_demo_data=true")
        return 0
    except Exception:
        db.rollback()
        print("seed failed — transaction rolled back", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
