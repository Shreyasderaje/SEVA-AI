"""Donation and taxonomy schemas."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

DonationStatus = Literal[
    "pending",
    "offered",
    "accepted",
    "pickup_scheduled",
    "picked_up",
    "completed",
    "cancelled",
]


class SubcategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    display_name: str
    subcategories: list[SubcategoryOut] = []


class DonationImageOut(BaseModel):
    id: str
    position: int
    mime_type: str
    size_bytes: int
    url: str


class DonationHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    from_status: str | None
    to_status: str
    note: str | None
    created_at: datetime


class DonationSummaryOut(BaseModel):
    id: str
    reference: str
    title: str
    status: DonationStatus
    quantity: float
    unit: str
    category_code: str
    category_display_name: str
    subcategory_display_name: str | None
    ai_predicted_category: str | None
    ai_confidence: float | None
    primary_image_url: str | None
    created_at: datetime


class DonationDetailOut(DonationSummaryOut):
    description: str | None
    condition: str | None
    pickup_area: str | None
    pickup_latitude: float | None
    pickup_longitude: float | None
    location_consent: bool
    pickup_window_start: datetime | None
    pickup_window_end: datetime | None
    images: list[DonationImageOut]
    timeline: list[DonationHistoryOut]


class DonationSummaryCounts(BaseModel):
    """Donor dashboard cards (§8.4). Grouping documented in BUILD_LOG:
    active = pending + offered; accepted = accepted + pickup_scheduled +
    picked_up; completed = completed."""

    active: int
    accepted: int
    completed: int
    total: int
