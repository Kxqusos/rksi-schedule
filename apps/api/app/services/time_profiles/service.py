from __future__ import annotations

from app.models import AuditLog, DayTimeProfile, WeekTimeProfile
from app.services.auth.permissions import Actor
from app.services.time_profiles import repository


class DuplicateTimeProfileError(Exception):
    pass


class TimeProfileNotFoundError(Exception):
    pass


class TimeProfileInUseError(Exception):
    pass


class DayProfileReferenceError(Exception):
    pass


def list_day_profiles(session) -> list[tuple[DayTimeProfile, list]]:
    profiles = repository.get_all_day_profiles(session)
    return [(p, repository.get_day_profile_slots(session, p.id)) for p in profiles]


def create_day_profile(session, name: str, slots, actor: Actor) -> tuple[DayTimeProfile, list]:
    name = name.strip()
    if repository.find_day_profile_by_name(session, name) is not None:
        raise DuplicateTimeProfileError()

    profile = DayTimeProfile(name=name)
    session.add(profile)
    session.flush()
    repository.replace_day_slots(session, profile.id, slots)
    session.flush()
    _audit(session, entity_type="day_time_profile", entity_id=profile.id, action="create", actor=actor, payload={"name": name})
    return profile, repository.get_day_profile_slots(session, profile.id)


def update_day_profile(session, profile_id: int, name: str, slots, actor: Actor) -> tuple[DayTimeProfile, list]:
    profile = repository.get_day_profile_by_id(session, profile_id)
    if profile is None:
        raise TimeProfileNotFoundError()

    name = name.strip()
    if repository.find_day_profile_by_name(session, name, exclude_id=profile_id) is not None:
        raise DuplicateTimeProfileError()

    profile.name = name
    repository.replace_day_slots(session, profile.id, slots)
    session.flush()
    _audit(session, entity_type="day_time_profile", entity_id=profile.id, action="update", actor=actor, payload={"name": name})
    return profile, repository.get_day_profile_slots(session, profile.id)


def delete_day_profile(session, profile_id: int, actor: Actor) -> None:
    profile = repository.get_day_profile_by_id(session, profile_id)
    if profile is None:
        raise TimeProfileNotFoundError()
    if repository.count_week_profiles_using_day_profile(session, profile_id) > 0:
        raise TimeProfileInUseError()

    from sqlalchemy import delete as sa_delete
    from app.models import DayTimeProfileSlot
    session.execute(sa_delete(DayTimeProfileSlot).where(DayTimeProfileSlot.day_profile_id == profile_id))
    _audit(session, entity_type="day_time_profile", entity_id=profile.id, action="delete", actor=actor, payload={"name": profile.name})
    session.delete(profile)


def list_week_profiles(session) -> list[tuple[WeekTimeProfile, list]]:
    profiles = repository.get_all_week_profiles(session)
    return [(p, repository.get_week_profile_days_with_names(session, p.id)) for p in profiles]


def create_week_profile(session, name: str, days, actor: Actor) -> tuple[WeekTimeProfile, list]:
    name = name.strip()
    if repository.find_week_profile_by_name(session, name) is not None:
        raise DuplicateTimeProfileError()
    if not repository.check_day_profiles_exist(session, [d.day_profile_id for d in days]):
        raise DayProfileReferenceError()

    profile = WeekTimeProfile(name=name)
    session.add(profile)
    session.flush()
    repository.replace_week_days(session, profile.id, days)
    session.flush()
    _audit(session, entity_type="week_time_profile", entity_id=profile.id, action="create", actor=actor, payload={"name": name})
    return profile, repository.get_week_profile_days_with_names(session, profile.id)


def update_week_profile(session, profile_id: int, name: str, days, actor: Actor) -> tuple[WeekTimeProfile, list]:
    profile = repository.get_week_profile_by_id(session, profile_id)
    if profile is None:
        raise TimeProfileNotFoundError()
    name = name.strip()
    if repository.find_week_profile_by_name(session, name, exclude_id=profile_id) is not None:
        raise DuplicateTimeProfileError()
    if not repository.check_day_profiles_exist(session, [d.day_profile_id for d in days]):
        raise DayProfileReferenceError()

    profile.name = name
    repository.replace_week_days(session, profile.id, days)
    session.flush()
    _audit(session, entity_type="week_time_profile", entity_id=profile.id, action="update", actor=actor, payload={"name": name})
    return profile, repository.get_week_profile_days_with_names(session, profile.id)


def delete_week_profile(session, profile_id: int, actor: Actor) -> None:
    profile = repository.get_week_profile_by_id(session, profile_id)
    if profile is None:
        raise TimeProfileNotFoundError()

    from sqlalchemy import delete as sa_delete
    from app.models import WeekTimeProfileDay
    session.execute(sa_delete(WeekTimeProfileDay).where(WeekTimeProfileDay.week_profile_id == profile_id))
    _audit(session, entity_type="week_time_profile", entity_id=profile.id, action="delete", actor=actor, payload={"name": profile.name})
    session.delete(profile)


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
