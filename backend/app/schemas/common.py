"""Shared Pydantic schemas."""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Server-side pagination envelope used by all list endpoints."""

    items: list[T]
    total: int
    page: int
    page_size: int


class Message(BaseModel):
    message: str
