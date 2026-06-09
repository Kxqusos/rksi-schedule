from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


UserRole = Literal["operator", "admin"]


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    role: UserRole


class UserResponse(BaseModel):
    id: int
    username: str
    role: UserRole
    created_at: datetime
