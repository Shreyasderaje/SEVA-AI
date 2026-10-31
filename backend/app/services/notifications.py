"""In-app notification service (§7 — in-app ONLY, no email/SMS/push).

Notifications are created transactionally alongside the workflow that causes
them: callers invoke `notify` inside their transaction so a rollback removes
the notification too.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.support import Notification


def notify(
    db: Session,
    *,
    user_id: str,
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
) -> None:
    """Queue one notification inside the caller's transaction, with a
    per-user monotonic seq for stable ordering."""
    next_seq = db.scalar(
        select(func.coalesce(func.max(Notification.seq), 0)).where(
            Notification.user_id == user_id
        )
    ) or 0
    db.add(
        Notification(
            user_id=user_id,
            type=type,
            title=title[:150],
            body=body[:2000] if body else None,
            link=link[:255] if link else None,
            seq=next_seq + 1,
        )
    )


def list_for_user(db: Session, user_id: str, *, page: int, page_size: int) -> dict:
    total = db.scalar(
        select(func.count()).select_from(Notification).where(Notification.user_id == user_id)
    ) or 0
    unread = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    ) or 0
    rows = db.scalars(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.seq.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "body": n.body,
                "link": n.link,
                "read": n.read_at is not None,
                "created_at": n.created_at.isoformat(),
            }
            for n in rows
        ],
        "total": total,
        "unread": unread,
        "page": page,
        "page_size": page_size,
    }
