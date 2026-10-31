"""Declarative base import shim.

Kept as a separate module so model modules can import `Base` without a circular
import through `app.core.database`'s engine setup.
"""

from app.core.database import Base

__all__ = ["Base"]
