from __future__ import annotations

from sqlalchemy import delete, func, select

from app.models import DayTimeProfile, DayTimeProfileSlot, WeekTimeProfile, WeekTimeProfileDay


def get_all_day_profiles(session) -> list[DayTimeProfile]:
    return session.scalars(select(DayTimeProfile).order_by(DayTimeProfile.id)).all()


def get_day_profile_by_id(session, profile_id: int) -> DayTimeProfile | None:
    return session.get(DayTimeProfile, profile_id)


def find_day_profile_by_name(session, name: str, *, exclude_id: int | None = None) -> int | None:
    stmt = select(DayTimeProfile.id).where(DayTimeProfile.name == name)
    if exclude_id is not None:
        stmt = stmt.where(DayTimeProfile.id != exclude_id)
    return session.scalar(stmt)


def get_day_profile_slots(session, profile_id: int) -> list[DayTimeProfileSlot]:
    return session.scalars(
        select(DayTimeProfileSlot)
        .where(DayTimeProfileSlot.day_profile_id == profile_id)
        .order_by(DayTimeProfileSlot.slot_number)
    ).all()


def replace_day_slots(session, profile_id: int, slots) -> None:
    session.execute(delete(DayTimeProfileSlot).where(DayTimeProfileSlot.day_profile_id == profile_id))
    for slot in sorted(slots, key=lambda s: s.slot_number):
        session.add(
            DayTimeProfileSlot(
                day_profile_id=profile_id,
                slot_number=slot.slot_number,
                time_start=slot.time_start,
                time_end=slot.time_end,
            )
        )


def count_week_profiles_using_day_profile(session, profile_id: int) -> int:
    return session.scalar(
        select(func.count(WeekTimeProfileDay.id)).where(WeekTimeProfileDay.day_profile_id == profile_id)
    ) or 0


def get_all_week_profiles(session) -> list[WeekTimeProfile]:
    return session.scalars(select(WeekTimeProfile).order_by(WeekTimeProfile.id)).all()


def get_week_profile_by_id(session, profile_id: int) -> WeekTimeProfile | None:
    return session.get(WeekTimeProfile, profile_id)


def find_week_profile_by_name(session, name: str, *, exclude_id: int | None = None) -> int | None:
    stmt = select(WeekTimeProfile.id).where(WeekTimeProfile.name == name)
    if exclude_id is not None:
        stmt = stmt.where(WeekTimeProfile.id != exclude_id)
    return session.scalar(stmt)


def get_week_profile_days_with_names(session, profile_id: int) -> list[tuple]:
    return session.execute(
        select(WeekTimeProfileDay, DayTimeProfile.name)
        .join(DayTimeProfile, DayTimeProfile.id == WeekTimeProfileDay.day_profile_id)
        .where(WeekTimeProfileDay.week_profile_id == profile_id)
        .order_by(WeekTimeProfileDay.weekday)
    ).all()


def replace_week_days(session, profile_id: int, days) -> None:
    session.execute(delete(WeekTimeProfileDay).where(WeekTimeProfileDay.week_profile_id == profile_id))
    for day in sorted(days, key=lambda d: d.weekday):
        session.add(
            WeekTimeProfileDay(
                week_profile_id=profile_id,
                weekday=day.weekday,
                day_profile_id=day.day_profile_id,
            )
        )


def check_day_profiles_exist(session, profile_ids: list[int]) -> bool:
    existing_ids = set(session.scalars(select(DayTimeProfile.id).where(DayTimeProfile.id.in_(profile_ids))).all())
    return existing_ids == set(profile_ids)
