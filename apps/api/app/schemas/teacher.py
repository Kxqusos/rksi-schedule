from __future__ import annotations

from datetime import date as Date

from pydantic import BaseModel, Field
from pydantic import model_validator


class TeacherCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    teacher_id: str | None = Field(default=None, max_length=100)
    post: str = Field(default="", max_length=200)


class TeacherAbsenceCreateRequest(BaseModel):
    date: Date
    all_day: bool = False
    time_slot_start: int | None = Field(default=None, ge=1, le=7)
    time_slot_end: int | None = Field(default=None, ge=1, le=7)
    reason: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def validate_slots(self):
        if self.all_day:
            self.time_slot_start = 1
            self.time_slot_end = 7
            return self
        if self.time_slot_start is None or self.time_slot_end is None:
            raise ValueError("time_slot_start and time_slot_end are required when all_day is false")
        if self.time_slot_start > self.time_slot_end:
            raise ValueError("time_slot_start must be less than or equal to time_slot_end")
        return self


class TeacherAbsenceResponse(BaseModel):
    id: int
    date: Date
    all_day: bool
    time_slot_start: int
    time_slot_end: int
    reason: str


class TeacherResponse(BaseModel):
    id: int
    teacher_id: str
    name: str
    post: str
    lesson_count: int
    absences: list[TeacherAbsenceResponse] = Field(default_factory=list)
