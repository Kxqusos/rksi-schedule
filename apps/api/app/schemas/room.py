from __future__ import annotations

from pydantic import BaseModel, Field


class RoomCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RoomResponse(BaseModel):
    id: int
    name: str
    building: str
    lesson_count: int
