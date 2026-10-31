"""Authorized file serving. Files live outside the web root (§11) and are
reachable only through this ownership-checked endpoint."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.donation import Donation, DonationImage
from app.services.storage import resolve_stored_path

router = APIRouter(prefix="/api/images", tags=["images"])


@router.get("/{image_id}")
def serve_image(
    image_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> FileResponse:
    image = db.get(DonationImage, image_id)
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    donation = db.get(Donation, image.donation_id)
    if donation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    if donation.donor_id != user.id and user.role != "admin":
        # 404 rather than 403: do not reveal other users' file existence.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return FileResponse(resolve_stored_path(image.stored_path), media_type=image.mime_type)
