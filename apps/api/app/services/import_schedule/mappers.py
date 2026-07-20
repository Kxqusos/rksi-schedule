from __future__ import annotations

from app.schemas.import_schedule import ImportScheduleResponse
from app.services.import_schedule.service import ImportResult


def import_result_to_response(result: ImportResult) -> ImportScheduleResponse:
    return ImportScheduleResponse(
        timetable_count=result.timetable_count,
        group_count=result.group_count,
        lesson_count=result.lesson_count,
        empty_day_count=result.empty_day_count,
    )
