"""Organization and verification schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    org_type: str | None
    description: str | None
    address: str | None
    verification_status: str
    rejection_reason: str | None
    verified_at: datetime | None
    created_at: datetime


class OrganizationApplicationOut(OrganizationOut):
    """Owner/admin view: adds contact details and coordinates.

    Coordinates are stored only with explicit consent at application time, so
    their presence IS the consent record (no separate flag is stored)."""

    latitude: float | None
    longitude: float | None
    contact_email: str | None
    contact_phone: str | None
    representative_name: str | None
    owner_user_id: str


class OrganizationPublicOut(BaseModel):
    """Public directory entry — no contact details, no documents."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    org_type: str | None
    description: str | None
    address: str | None
    verified_at: datetime | None


class VerificationDecision(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class AdminOrganizationOut(OrganizationApplicationOut):
    document_id: str | None = None
    document_url: str | None = None


class OrganizationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    org_type: str | None
    verification_status: str
    created_at: datetime


VerificationStatus = Literal[
    "pending_verification", "verified", "rejected", "suspended"
]
