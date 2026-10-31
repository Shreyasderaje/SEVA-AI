"""Password hashing (bcrypt) and JWT access tokens (pyjwt).

The token payload contains only the user id and role (§11 of the master prompt).
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str, role: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_effective, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Return the payload, or None when the token is invalid or expired."""
    try:
        return jwt.decode(token, get_settings().jwt_secret_effective, algorithms=[_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
