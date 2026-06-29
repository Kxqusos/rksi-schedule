from __future__ import annotations

from app.models import DayTimeProfile, DayTimeProfileSlot, WeekTimeProfile, WeekTimeProfileDay
from app.schemas.time_profile import (
    DayTimeProfileResponse,
    DayTimeProfileSlotResponse,
    WeekTimeProfileDayResponse,
    WeekTimeProfileResponse,
)


def day_profile_to_response(profile: DayTimeProfile, slots: list[DayTimeProfileSlot]) -> DayTimeProfileResponse:
    return DayTimeProfileResponse(
        id=profile.id,
        name=profile.name,
        created_at=profile.created_at,
        slots=[
            DayTimeProfileSlotResponse(
                slot_number=slot.slot_number,
                time_start=slot.time_start,
                time_end=slot.time_end,
            )
            for slot in slots
        ],
    )


def week_profile_to_response(profile: WeekTimeProfile, days_with_names: list[tuple]) -> WeekTimeProfileResponse:
    return WeekTimeProfileResponse(
        id=profile.id,
        name=profile.name,
        created_at=profile.created_at,
        days=[
            WeekTimeProfileDayResponse(
                weekday=day.weekday,
                day_profile_id=day.day_profile_id,
                day_profile_name=day_profile_name,
            )
            for day, day_profile_name in days_with_names
        ],
    )
