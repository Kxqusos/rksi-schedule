from __future__ import annotations

from datetime import date as Date
from datetime import time as Time

from pydantic import BaseModel, Field


class LessonCreateRequest(BaseModel):
    group_name: str
    course: int = 0
    faculty: str = ""
    subject: str
    teacher_name: str | None = None
    teacher_id: str | None = None
    teacher_post: str = ""
    room_name: str | None = None
    date: Date
    time_start: Time
    time_end: Time
    weekday: int = Field(ge=1, le=7)
    week_number: int
    time_slot: int = Field(ge=1)
    subgroup: int = Field(default=0, ge=0)
    lesson_type: str = ""


class LessonUpdateRequest(BaseModel):
    group_name: str | None = None
    course: int | None = None
    faculty: str | None = None
    subject: str | None = None
    teacher_name: str | None = None
    teacher_id: str | None = None
    teacher_post: str | None = None
    room_name: str | None = None
    date: Date | None = None
    time_start: Time | None = None
    time_end: Time | None = None
    weekday: int | None = Field(default=None, ge=1, le=7)
    week_number: int | None = None
    time_slot: int | None = Field(default=None, ge=1)
    subgroup: int | None = Field(default=None, ge=0)
    lesson_type: str | None = None


class LessonResponse(BaseModel):
    id: int
    group_name: str
    subject: str
    teacher_name: str | None
    room_name: str | None
    date: Date
    time_start: Time
    time_end: Time
    weekday: int
    week_number: int
    time_slot: int
    subgroup: int
    lesson_type: str


class ScheduleProblemResponse(BaseModel):
    severity: str
    code: str
    message: str
    date: Date | None = None
    week_number: int | None = None
    time_slot: int | None = None
    group_name: str | None = None
    teacher_name: str | None = None
    room_name: str | None = None
    lesson_ids: list[int] = Field(default_factory=list)


class ScheduleSlotRoomResponse(BaseModel):
    room_name: str
    building: str
    lesson: LessonResponse | None
