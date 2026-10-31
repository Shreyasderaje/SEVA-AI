"""Append-only audit logging (§6.7).

Rows are inserted within the caller's transaction; there is no update or delete
path for audit rows anywhere in the application.
"""

import hashlib

from sqlalchemy.orm import Session

from app.models.support import AuditLog


def hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def log_audit(
    db: Session,
    *,
    actor_user_id: str | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    note: str | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            note=note[:500] if note else None,
            ip_hash=hash_ip(ip) if ip else None,
        )
    )
