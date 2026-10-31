"""Rate limiting via slowapi (in-memory storage, appropriate for this MVP).

Applied to login, registration, and (in later milestones) file-upload endpoints.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    headers_enabled=True,
)


def reset_rate_limiter() -> None:
    """Clear in-memory counters (used between tests to isolate rate limits)."""
    inner = getattr(limiter, "limiter", None) or limiter
    storage = getattr(inner, "storage", None)
    if storage is not None:
        try:
            storage.reset()
        except Exception:  # pragma: no cover - defensive; never break a test teardown
            pass
