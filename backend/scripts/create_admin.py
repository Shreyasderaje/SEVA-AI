"""Create the seeded admin account and base reference data.

Idempotent — safe to run any number of times. This script is NOT the demo
seeder (`seed_demo.py`, milestone M5); it creates operational base data:

- the single admin account (no public admin registration exists),
- the five FIXED donation categories (classifier classes),
- example display subcategories (addendum §3),
- default matching settings (weights, service radius),
- self-compatibility rows for the matching engine.

The admin account is deliberately NOT marked `is_demo_data`, so the M5 demo
reset can never delete it.

Usage (from backend/):  python scripts/create_admin.py
"""

import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.constants import (  # noqa: E402
    CLASSIFIER_CLASSES,
    DEFAULT_MATCHING_WEIGHTS,
    ROLE_ADMIN,
    SUBCATEGORY_EXAMPLES,
)
from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.app_settings import Setting  # noqa: E402
from app.models.donation import (  # noqa: E402
    DonationCategory,
    DonationCompatibility,
    DonationSubcategory,
)
from app.models.user import User  # noqa: E402

DEFAULT_ADMIN_EMAIL = "admin@seva.example"


def seed_settings(db) -> None:
    defaults = {
        "matching_weights": DEFAULT_MATCHING_WEIGHTS,
        "service_radius_km": 50.0,
    }
    for key, value in defaults.items():
        import json

        if db.get(Setting, key) is None:
            db.add(Setting(key=key, value_json=json.dumps(value)))
            print(f"  settings: added '{key}'")


def seed_categories(db) -> dict[str, object]:
    categories: dict[str, object] = {}
    for code, display in CLASSIFIER_CLASSES:
        row = db.scalar(select(DonationCategory).where(DonationCategory.code == code))
        if row is None:
            row = DonationCategory(code=code, display_name=display, is_active=True)
            db.add(row)
            db.flush()
            print(f"  donation_categories: added '{code}'")
        categories[code] = row
    # Self-compatibility (exact) rows for the matching engine.
    for code, row in categories.items():
        exists = db.get(DonationCompatibility, (row.id, row.id))
        if exists is None:
            db.add(
                DonationCompatibility(
                    donation_category_id=row.id, need_category_id=row.id, factor="exact"
                )
            )
    return categories


def seed_subcategories(db, categories: dict[str, object]) -> None:
    for code, names in SUBCATEGORY_EXAMPLES.items():
        parent = categories[code]
        for order, name in enumerate(names):
            exists = db.scalar(
                select(DonationSubcategory).where(
                    DonationSubcategory.category_id == parent.id,  # type: ignore[attr-defined]
                    DonationSubcategory.display_name == name,
                )
            )
            if exists is None:
                db.add(
                    DonationSubcategory(
                        category_id=parent.id,  # type: ignore[attr-defined]
                        display_name=name,
                        sort_order=order,
                        is_active=True,
                    )
                )


def seed_admin(db) -> None:
    email = os.environ.get("SEVA_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        print(f"  admin account '{email}' already exists — skipping")
        return
    password = os.environ.get("SEVA_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
    db.add(
        User(
            email=email,
            password_hash=hash_password(password),
            full_name="SEVA-AI Admin",
            role=ROLE_ADMIN,
        )
    )
    if os.environ.get("SEVA_ADMIN_PASSWORD"):
        print(f"  admin account '{email}' created with the password from SEVA_ADMIN_PASSWORD")
    else:
        print()
        print("=" * 60)
        print(f"  Admin account: {email}")
        print(f"  Generated password (printed ONCE, store it now): {password}")
        print("=" * 60)
        print()


def main() -> None:
    print("Seeding base data (idempotent)...")
    db = SessionLocal()
    try:
        seed_settings(db)
        categories = seed_categories(db)
        seed_subcategories(db, categories)
        seed_admin(db)
        db.commit()
        print("Done.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
