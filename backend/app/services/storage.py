"""Storage service: validated, re-encoded upload storage outside the web root.

Rules implemented here (§6.5, §11, addendum §8):
- Magic-byte checks — never trust the filename, extension, or client MIME type.
- Size limits enforced on the actual bytes.
- Uploaded filenames are discarded; files are stored under generated UUID names.
- Images are re-encoded (resized, metadata/EXIF stripped) before storage.
- Files live under STORAGE_DIR (outside the web root) and are served only
  through authorized backend endpoints.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image

from app.core.config import get_settings

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB per donation image (§6.5)
MAX_IMAGE_DIMENSION = 1600  # resized long edge; also guarantees EXIF removal via re-encode
JPEG_QUALITY = 85

# magic-number signatures → canonical MIME we accept for donation images
IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


@dataclass
class StoredImage:
    stored_path: str  # relative to the storage root
    mime_type: str
    size_bytes: int
    sha256: str


def detect_image_mime(data: bytes) -> str | None:
    """Return the MIME type implied by the file's magic bytes, or None.

    WebP is handled separately: RIFF....WEBP (bytes 8-12)."""
    for signature, mime in IMAGE_SIGNATURES:
        if data.startswith(signature):
            return mime
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _validate_image_bytes(data: bytes) -> None:
    if len(data) == 0:
        raise HTTPException(422, "The uploaded image is empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(422, "Each image must be 5 MB or smaller")
    if detect_image_mime(data) is None:
        raise HTTPException(
            422, "Unsupported image type. Upload a JPEG, PNG, or WebP image."
        )


def _reencode_as_jpeg(data: bytes) -> bytes:
    """Decode, strip all metadata, cap the long edge, and re-encode as JPEG."""
    try:
        with Image.open(BytesIO(data)) as image:
            image = image.convert("RGB")
            image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))
            buffer = BytesIO()
            image.save(buffer, "JPEG", quality=JPEG_QUALITY)
            return buffer.getvalue()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — a corrupt image is a user error
        raise HTTPException(422, "The image could not be processed") from exc


def storage_root() -> Path:
    root = get_settings().storage_path
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_stored_path(stored_path: str) -> Path:
    """Resolve a stored relative path, refusing escapes from the storage root."""
    root = storage_root()
    candidate = (root / stored_path).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    if not candidate.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return candidate


async def save_donation_image(upload: UploadFile, donation_id: str) -> StoredImage:
    """Validate and store one donation image. Position is assigned by the caller."""
    import hashlib

    data = await upload.read()
    _validate_image_bytes(data)  # raises 422 with no file written

    reencoded = _reencode_as_jpeg(data)  # strips EXIF/metadata, resizes

    relative = Path("donations") / donation_id / f"{uuid.uuid4().hex}.jpg"
    destination = storage_root() / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(reencoded)

    return StoredImage(
        stored_path=relative.as_posix(),
        mime_type="image/jpeg",
        size_bytes=len(reencoded),
        sha256=hashlib.sha256(reencoded).hexdigest(),
    )


async def read_upload(upload: UploadFile, *, max_bytes: int, label: str) -> bytes:
    """Read an UploadFile enforcing a size limit (shared by future endpoints)."""
    data = await upload.read()
    if len(data) > max_bytes:
        raise HTTPException(422, f"{label} must be {max_bytes // (1024 * 1024)} MB or smaller")
    return data
