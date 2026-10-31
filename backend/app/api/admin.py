"""Admin-only endpoints. M1 exposes the user list (real functionality used by
the M5 admin dashboard); verification queues and dashboards come later."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import ROLE_ADMIN
from app.core.database import get_db
from app.core.deps import require_roles
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.common import Page

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)


@router.get("/users", response_model=Page[UserOut])
def list_users(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[UserOut]:
    total = db.scalar(select(func.count()).select_from(User)) or 0
    rows = db.scalars(
        select(User)
        .order_by(User.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
