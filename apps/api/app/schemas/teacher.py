from __future__ import annotations

from pydantic import BaseModel, Field


class TeacherCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    teacher_id: str | None = Field(default=None, max_length=100)
    post: str = Field(default="", max_length=200)


class TeacherResponse(BaseModel):
    id: int
    teacher_id: str
    name: str
    post: str
    lesson_count: int
