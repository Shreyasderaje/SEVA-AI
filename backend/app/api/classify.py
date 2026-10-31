"""Donation image classification endpoint (addendum §4, §10; master §6.5).

The donor's client sends ONLY the primary image (the first uploaded photo) —
supporting photographs are never classified in the MVP. When the trained
five-class model is not configured, this endpoint returns the documented
`model_not_configured` status with HTTP 200 and the UI switches to manual
category selection. No fabricated predictions, ever.
"""

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import ROLE_DONOR
from app.core.database import get_db
from app.core.deps import require_roles
from app.core.rate_limit import limiter
from app.ml.classifier import predict
from app.services.storage import _validate_image_bytes  # shared validation, no storage

router = APIRouter(prefix="/api/classify", tags=["classifier"])


@router.post("")
@limiter.limit(get_settings().rate_limit_login)  # uploads are rate-limited (§11)
async def classify_image(
    request: Request,
    image: UploadFile,
    user=Depends(require_roles(ROLE_DONOR)),
    db: Session = Depends(get_db),  # noqa: ARG001 — dependency enforces the session
) -> JSONResponse:
    image_bytes = await image.read()
    _validate_image_bytes(image_bytes)  # 422 on wrong type/size, nothing stored

    result = predict(image_bytes)
    if result is None:
        payload = {"status": "model_not_configured"}
    else:
        payload = {"status": "ok", **result}
    # slowapi requires rate-limited endpoints to return a Starlette Response.
    return JSONResponse(content=payload)
