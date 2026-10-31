"""Notification endpoints — strictly per-user (§7)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.models.support import Notification
from app.models.user import User
from app.services.notifications import list_for_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def my_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict:
    return list_for_user(db, user.id, page=page, page_size=page_size)


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: str,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(404, "Notification not found")
    if notification.read_at is None:
        notification.read_at = datetime.now()
        db.commit()
    return {"message": "Marked as read"}


@router.post("/read-all")
def mark_all_read(
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict:
    notifications = db.scalars(
        select(Notification).where(
            Notification.user_id == user.id, Notification.read_at.is_(None)
        )
    ).all()
    now = datetime.now()
    for notification in notifications:
        notification.read_at = now
    db.commit()
    return {"message": f"Marked {len(notifications)} notification(s) as read"}
