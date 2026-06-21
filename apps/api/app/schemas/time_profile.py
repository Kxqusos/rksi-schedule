from __future__ import annotations

from datetime import datetime
from datetime import time as Time

from pydantic import BaseModel, Field, model_validator


class DayTimeProfileSlotRequest(BaseModel):
    slot_number: int = Field(ge=1, le=7)
    time_start: Time
    time_end: Time

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.time_start >= self.time_end:
            raise ValueError("time_start must be less than time_end")
        return self


class DayTimeProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    slots: list[DayTimeProfileSlotRequest]

    @model_validator(mode="after")
    def validate_slots(self):
        slot_numbers = [slot.slot_number for slot in self.slots]
        if sorted(slot_numbers) != [1, 2, 3, 4, 5, 6, 7]:
            raise ValueError("day profile must contain exactly seven unique slots from 1 to 7")
        return self


class DayTimeProfileUpdateRequest(DayTimeProfileCreateRequest):
    pass


class DayTimeProfileSlotResponse(BaseModel):
    slot_number: int
    time_start: Time
    time_end: Time


class DayTimeProfileResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    slots: list[DayTimeProfileSlotResponse]


class WeekTimeProfileDayRequest(BaseModel):
    weekday: int = Field(ge=1, le=7)
    day_profile_id: int


class WeekTimeProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    days: list[WeekTimeProfileDayRequest]

    @model_validator(mode="after")
    def validate_days(self):
        weekdays = [day.weekday for day in self.days]
        if sorted(weekdays) != [1, 2, 3, 4, 5, 6, 7]:
            raise ValueError("week profile must contain exactly seven unique weekdays from 1 to 7")
        return self


class WeekTimeProfileUpdateRequest(WeekTimeProfileCreateRequest):
    pass


class WeekTimeProfileDayResponse(BaseModel):
    weekday: int
    day_profile_id: int
    day_profile_name: str


class WeekTimeProfileResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    days: list[WeekTimeProfileDayResponse]
