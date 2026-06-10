from __future__ import annotations

from pydantic import BaseModel, Field


class RoomCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RoomExclusionRequest(BaseModel):
    reason: str = Field(default="", max_length=300)


class RoomResponse(BaseModel):
    id: int
    name: str
    building: str
    lesson_count: int
    is_excluded: bool
    exclusion_reason: str
