from __future__ import annotations

from sqlalchemy import delete, func, select

from app.models import (
    AuditLog,
    DayTimeProfile,
    DayTimeProfileSlot,
    WeekTimeProfile,
    WeekTimeProfileDay,
)
from app.schemas.time_profile import (
    DayTimeProfileCreateRequest,
    DayTimeProfileResponse,
    DayTimeProfileSlotResponse,
    DayTimeProfileUpdateRequest,
    WeekTimeProfileCreateRequest,
    WeekTimeProfileDayResponse,
    WeekTimeProfileResponse,
    WeekTimeProfileUpdateRequest,
)
from app.services.auth.permissions import Actor


class DuplicateTimeProfileError(Exception):
    pass


class TimeProfileNotFoundError(Exception):
    pass


class TimeProfileInUseError(Exception):
    pass


class DayProfileReferenceError(Exception):
    pass


def list_day_profiles(session) -> list[DayTimeProfileResponse]:
    profiles = session.scalars(select(DayTimeProfile).order_by(DayTimeProfile.id)).all()
    return [_day_profile_response(session, profile) for profile in profiles]


def create_day_profile(session, payload: DayTimeProfileCreateRequest, actor: Actor) -> DayTimeProfileResponse:
    name = payload.name.strip()
    if session.scalar(select(DayTimeProfile.id).where(DayTimeProfile.name == name)) is not None:
        raise DuplicateTimeProfileError()

    profile = DayTimeProfile(name=name)
    session.add(profile)
    session.flush()
    _replace_day_slots(session, profile.id, payload)
    session.flush()
    _audit(session, entity_type="day_time_profile", entity_id=profile.id, action="create", actor=actor, payload={"name": name})
    return _day_profile_response(session, profile)


def update_day_profile(session, profile_id: int, payload: DayTimeProfileUpdateRequest, actor: Actor) -> DayTimeProfileResponse:
    profile = session.get(DayTimeProfile, profile_id)
    if profile is None:
        raise TimeProfileNotFoundError()

    name = payload.name.strip()
    duplicate_id = session.scalar(select(DayTimeProfile.id).where(DayTimeProfile.name == name, DayTimeProfile.id != profile_id))
    if duplicate_id is not None:
        raise DuplicateTimeProfileError()

    profile.name = name
    _replace_day_slots(session, profile.id, payload)
    session.flush()
    _audit(session, entity_type="day_time_profile", entity_id=profile.id, action="update", actor=actor, payload={"name": name})
    return _day_profile_response(session, profile)


def delete_day_profile(session, profile_id: int, actor: Actor) -> None:
    profile = session.get(DayTimeProfile, profile_id)
    if profile is None:
        raise TimeProfileNotFoundError()
    usage_count = session.scalar(select(func.count(WeekTimeProfileDay.id)).where(WeekTimeProfileDay.day_profile_id == profile_id)) or 0
    if usage_count > 0:
        raise TimeProfileInUseError()

    session.execute(delete(DayTimeProfileSlot).where(DayTimeProfileSlot.day_profile_id == profile_id))
    _audit(session, entity_type="day_time_profile", entity_id=profile.id, action="delete", actor=actor, payload={"name": profile.name})
    session.delete(profile)


def list_week_profiles(session) -> list[WeekTimeProfileResponse]:
    profiles = session.scalars(select(WeekTimeProfile).order_by(WeekTimeProfile.id)).all()
    return [_week_profile_response(session, profile) for profile in profiles]


def create_week_profile(session, payload: WeekTimeProfileCreateRequest, actor: Actor) -> WeekTimeProfileResponse:
    name = payload.name.strip()
    if session.scalar(select(WeekTimeProfile.id).where(WeekTimeProfile.name == name)) is not None:
        raise DuplicateTimeProfileError()
    _ensure_day_profiles_exist(session, [day.day_profile_id for day in payload.days])

    profile = WeekTimeProfile(name=name)
    session.add(profile)
    session.flush()
    _replace_week_days(session, profile.id, payload)
    session.flush()
    _audit(session, entity_type="week_time_profile", entity_id=profile.id, action="create", actor=actor, payload={"name": name})
    return _week_profile_response(session, profile)


def update_week_profile(session, profile_id: int, payload: WeekTimeProfileUpdateRequest, actor: Actor) -> WeekTimeProfileResponse:
    profile = session.get(WeekTimeProfile, profile_id)
    if profile is None:
        raise TimeProfileNotFoundError()
    name = payload.name.strip()
    duplicate_id = session.scalar(select(WeekTimeProfile.id).where(WeekTimeProfile.name == name, WeekTimeProfile.id != profile_id))
    if duplicate_id is not None:
        raise DuplicateTimeProfileError()
    _ensure_day_profiles_exist(session, [day.day_profile_id for day in payload.days])

    profile.name = name
    _replace_week_days(session, profile.id, payload)
    session.flush()
    _audit(session, entity_type="week_time_profile", entity_id=profile.id, action="update", actor=actor, payload={"name": name})
    return _week_profile_response(session, profile)


def delete_week_profile(session, profile_id: int, actor: Actor) -> None:
    profile = session.get(WeekTimeProfile, profile_id)
    if profile is None:
        raise TimeProfileNotFoundError()

    session.execute(delete(WeekTimeProfileDay).where(WeekTimeProfileDay.week_profile_id == profile_id))
    _audit(session, entity_type="week_time_profile", entity_id=profile.id, action="delete", actor=actor, payload={"name": profile.name})
    session.delete(profile)


def _replace_day_slots(session, profile_id: int, payload: DayTimeProfileCreateRequest | DayTimeProfileUpdateRequest) -> None:
    session.execute(delete(DayTimeProfileSlot).where(DayTimeProfileSlot.day_profile_id == profile_id))
    for slot in sorted(payload.slots, key=lambda item: item.slot_number):
        session.add(
            DayTimeProfileSlot(
                day_profile_id=profile_id,
                slot_number=slot.slot_number,
                time_start=slot.time_start,
                time_end=slot.time_end,
            )
        )


def _replace_week_days(session, profile_id: int, payload: WeekTimeProfileCreateRequest | WeekTimeProfileUpdateRequest) -> None:
    session.execute(delete(WeekTimeProfileDay).where(WeekTimeProfileDay.week_profile_id == profile_id))
    for day in sorted(payload.days, key=lambda item: item.weekday):
        session.add(
            WeekTimeProfileDay(
                week_profile_id=profile_id,
                weekday=day.weekday,
                day_profile_id=day.day_profile_id,
            )
        )


def _ensure_day_profiles_exist(session, profile_ids: list[int]) -> None:
    existing_ids = set(session.scalars(select(DayTimeProfile.id).where(DayTimeProfile.id.in_(profile_ids))).all())
    if existing_ids != set(profile_ids):
        raise DayProfileReferenceError()


def _day_profile_response(session, profile: DayTimeProfile) -> DayTimeProfileResponse:
    slots = session.scalars(
        select(DayTimeProfileSlot)
        .where(DayTimeProfileSlot.day_profile_id == profile.id)
        .order_by(DayTimeProfileSlot.slot_number)
    ).all()
    return DayTimeProfileResponse(
        id=profile.id,
        name=profile.name,
        created_at=profile.created_at,
        slots=[
            DayTimeProfileSlotResponse(slot_number=slot.slot_number, time_start=slot.time_start, time_end=slot.time_end)
            for slot in slots
        ],
    )


def _week_profile_response(session, profile: WeekTimeProfile) -> WeekTimeProfileResponse:
    rows = session.execute(
        select(WeekTimeProfileDay, DayTimeProfile.name)
        .join(DayTimeProfile, DayTimeProfile.id == WeekTimeProfileDay.day_profile_id)
        .where(WeekTimeProfileDay.week_profile_id == profile.id)
        .order_by(WeekTimeProfileDay.weekday)
    ).all()
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
            for day, day_profile_name in rows
        ],
    )


def _audit(session, *, entity_type: str, entity_id: int, action: str, actor: Actor, payload: dict) -> None:
    session.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_role=actor.role,
            actor_name=actor.name,
            payload=payload,
        )
    )
