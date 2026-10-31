"""Organization needs schemas."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NeedStatus = Literal["active", "paused", "closed", "fulfilled"]


class NeedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    organization_name: str | None = None
    category_id: str
    category_code: str | None = None
    category_display_name: str | None = None
    subcategory_id: str | None
    subcategory_display_name: str | None = None
    title: str
    description: str | None
    unit: str
    quantity_required: float
    quantity_fulfilled: float
    remaining_quantity: float
    urgency: str
    required_by: date | None
    status: NeedStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime


class NeedCreateRequest(BaseModel):
    category_id: str
    subcategory_id: str | None = None
    title: str = Field(min_length=3, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    unit: Literal["kg", "pieces", "packets", "sets", "litres"]
    quantity_required: float = Field(gt=0)
    urgency: Literal["low", "medium", "high", "critical"] = "medium"
    required_by: date | None = None
    notes: str | None = Field(default=None, max_length=1000)


class NeedUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    urgency: Literal["low", "medium", "high", "critical"] | None = None
    required_by: date | None = None
    notes: str | None = Field(default=None, max_length=1000)
    quantity_required: float | None = Field(default=None, gt=0)
    subcategory_id: str | None = None


class NeedFulfilmentRequest(BaseModel):
    quantity: float = Field(gt=0, description="Quantity to add to the fulfilled total")


class NeedStatusRequest(BaseModel):
    status: Literal["active", "paused", "closed"]
