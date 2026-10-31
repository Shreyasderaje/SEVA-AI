"""Auth request/response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=120)
    role: Literal["donor", "organization"]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str
    role: str
    status: str
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    user: UserOut
