"""SEVA-AI FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import admin, auth, health
from app.core.config import get_settings
from app.core.rate_limit import limiter

logger = logging.getLogger("seva")


def log_startup_diagnostics() -> None:
    """Log configuration facts at startup — never secrets (addendum §10)."""
    settings = get_settings()
    logger.info(
        "SEVA-AI API starting | env=%s | database=%s",
        settings.seva_env,
        settings.database_url.split(":", 1)[0],
    )
    logger.info("Storage directory: %s", settings.storage_path)
    weights = settings.classifier_weights_file
    logger.info(
        "Classifier weights resolved to %s | file present: %s",
        weights,
        weights.exists(),
    )
    if settings.is_development and (not settings.jwt_secret or settings.jwt_secret == "replace-me"):
        logger.warning(
            "JWT_SECRET is unset — using the insecure development fallback. "
            "Never run outside development this way."
        )
    # Fail fast outside development when no real secret is configured.
    settings.jwt_secret_effective


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_startup_diagnostics()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="SEVA-AI API",
        version="0.1.0",
        description="AI-Powered Smart Donation and Charity Resource Management System",
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(admin.router)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        # Consistent, safe error shape; no internal details leak through.
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        if settings.is_development:
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()
