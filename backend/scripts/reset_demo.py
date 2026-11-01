"""Demo reset script (M5 §4.4) — development ONLY.

Deletes ONLY rows explicitly marked `is_demo_data=True`, child records before
parent records, inside one transaction (rolled back entirely on failure).
Non-demo records (including the admin account and any real users) are never
touched.

Usage (from backend/):
    set SEVA_ENV=development  (PowerShell: $env:SEVA_ENV="development")
    .venv/Scripts/python.exe scripts/reset_demo.py            # shows summary, asks to confirm
    .venv/Scripts/python.exe scripts/reset_demo.py --yes      # skips the prompt
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.donation import (  # noqa: E402
    Donation,
    DonationImage,
)
from app.models.need import OrganizationNeed  # noqa: E402
from app.models.offer import DonationOffer, DonationStatusHistory  # noqa: E402
from app.models.organization import Organization, OrganizationDocument  # noqa: E402
from app.models.support import Notification, PaymentRecord  # noqa: E402
from app.models.user import DonorProfile, User  # noqa: E402
from app.services.storage import storage_root  # noqa: E402

# Child-first deletion order (respects actual foreign keys).
DELETE_ORDER: list[tuple[str, object, bool]] = [
    # (label, model, owner_user_id_is_the_link)
    ("notifications", Notification, False),
    ("payment_records", PaymentRecord, False),
    ("donation_offers", DonationOffer, False),
    ("donation_status_history", DonationStatusHistory, False),
    ("donation_images", DonationImage, False),
    ("donations", Donation, False),
    ("organization_needs", OrganizationNeed, False),
    ("organization_documents", OrganizationDocument, False),
    ("organizations", Organization, False),
    ("donor_profiles", DonorProfile, True),
    ("users (donor/organization demo accounts)", User, True),
]

# Storage subdirectories whose contents are demo-generated.
DEMO_STORAGE_DIRS = ("donations", "verification", "upi", "payment_receipts")


def _require_development() -> None:
    env = os.environ.get("SEVA_ENV", "").strip().lower()
    print(f"environment: SEVA_ENV={env or '(unspecified)'} | operation: reset demo data")
    if env != "development":
        sys.exit(
            "refusing to run: demo reset is allowed only with SEVA_ENV=development."
        )


def _demo_filter(model, link_to_user: bool):
    if link_to_user:
        return model.is_demo_data.is_(True)
    return model.is_demo_data.is_(True)


def _count_pending(db: Session) -> dict[str, int]:
    summary: dict[str, int] = {}
    for label, model, _link in DELETE_ORDER:
        if label.startswith("users"):
            # only demo donor/organization accounts (never the admin)
            summary[label] = (
                db.scalar(
                    select(func.count())
                    .select_from(User)
                    .where(
                        User.is_demo_data.is_(True),
                        User.role.in_(["donor", "organization"]),
                    )
                )
                or 0
            )
            continue
        summary[label] = db.scalar(
            select(func.count()).select_from(model).where(_demo_filter(model, False))
        ) or 0
    return summary


def _delete_all(db: Session) -> dict[str, int]:
    deleted: dict[str, int] = {}
    for label, model, link_to_user in DELETE_ORDER:
        statement = delete(model).where(_demo_filter(model, link_to_user))
        if label.startswith("users"):
            statement = delete(model).where(
                model.is_demo_data.is_(True),
                model.role.in_(["donor", "organization"]),
            )
        result = db.execute(statement)
        deleted[label] = result.rowcount or 0
    return deleted


def main() -> int:
    _require_development()
    db = SessionLocal()
    try:
        pending = _count_pending(db)
        total = sum(pending.values())
        print("demo records currently present:")
        for label, count in pending.items():
            print(f"  {label}: {count}")
        if total == 0:
            print("nothing to reset — no demo records found.")
            return 0

        if "--yes" not in sys.argv:
            answer = input(
                f"Delete {total} demo record(s)? Non-demo records are never touched. [y/N] "
            )
            if answer.strip().lower() not in ("y", "yes"):
                print("reset cancelled.")
                return 1

        deleted = _delete_all(db)
        db.commit()

        # Demo-generated uploads (demo photos/documents) are safe to remove;
        # non-demo uploads live in different per-id directories and are untouched.
        for subdir in DEMO_STORAGE_DIRS:
            directory = storage_root() / subdir
            if directory.is_dir():
                removed = 0
                for child in directory.iterdir():
                    import shutil

                    if child.is_dir():
                        # only remove directories whose rows are gone (demo ids)
                        shutil.rmtree(child, ignore_errors=True)
                        removed += 1
                if removed:
                    print(f"  storage/{subdir}: removed {removed} demo directories")

        print("demo reset complete:")
        for label, count in deleted.items():
            print(f"  {label}: {count} deleted")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"reset failed — transaction rolled back ({exc})", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
