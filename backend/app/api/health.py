"""Health check endpoint."""

from sqlalchemy import text

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    database = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database = "error"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "app": "SEVA-AI",
        "env": settings.seva_env,
        "database": database,
    }
