from __future__ import annotations

from pydantic import BaseModel


class ImportScheduleResponse(BaseModel):
    timetable_count: int
    group_count: int
    lesson_count: int
    empty_day_count: int
