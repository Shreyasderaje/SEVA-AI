"""Public taxonomy endpoint: fixed categories + admin-managed subcategories."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.donation import DonationCategory, DonationSubcategory
from app.schemas.donation import CategoryOut, SubcategoryOut

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)) -> list[CategoryOut]:
    categories = db.scalars(
        select(DonationCategory).where(DonationCategory.is_active.is_(True))
    ).all()
    subcategories = db.scalars(
        select(DonationSubcategory)
        .where(DonationSubcategory.is_active.is_(True))
        .order_by(DonationSubcategory.sort_order.asc())
    ).all()

    by_category: dict[str, list[SubcategoryOut]] = {}
    for sub in subcategories:
        by_category.setdefault(sub.category_id, []).append(SubcategoryOut.model_validate(sub))

    return [
        CategoryOut(
            id=category.id,
            code=category.code,
            display_name=category.display_name,
            subcategories=by_category.get(category.id, []),
        )
        for category in categories
    ]
