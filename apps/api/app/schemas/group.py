from __future__ import annotations

from pydantic import BaseModel, Field


class GroupUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class GroupHomeroomTeacherRequest(BaseModel):
    teacher_id: int | None = None


class GroupResponse(BaseModel):
    id: int
    name: str
    course: int
    faculty: str
    lesson_count: int
    homeroom_teacher_id: int | None = None
    homeroom_teacher_name: str | None = None
