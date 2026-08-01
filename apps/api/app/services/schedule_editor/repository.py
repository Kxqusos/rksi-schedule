from __future__ import annotations

from sqlalchemy import func, select

from app.models import Group, Lesson, Room, Subject, Teacher


def get_rooms_ordered(session) -> list[Room]:
    return session.scalars(select(Room).where(Room.is_excluded.is_(False)).order_by(Room.source_name)).all()


def get_lessons_for_slot(session, lesson_date, time_slot: int) -> list[Lesson]:
    return session.scalars(
        select(Lesson)
        .join(Group, Group.id == Lesson.group_id)
        .outerjoin(Room, Room.id == Lesson.room_id)
        .where(
            Lesson.lesson_date == lesson_date,
            Lesson.time_slot == time_slot,
        )
        .order_by(Room.source_name, Group.source_name, Lesson.subgroup)
    ).all()


def get_room_by_name(session, name: str) -> Room | None:
    return session.scalar(select(Room).where(Room.source_name == name))


def get_latest_lesson_date(session):
    return session.scalar(select(func.max(Lesson.lesson_date)))


def get_latest_week_number_for_date(session, lesson_date) -> int | None:
    return session.scalar(
        select(Lesson.week_number)
        .where(Lesson.lesson_date == lesson_date)
        .order_by(Lesson.week_number.desc())
        .limit(1)
    )


def get_lessons_for_week(session, week_start, week_end) -> list[Lesson]:
    return session.scalars(
        select(Lesson)
        .where(Lesson.lesson_date >= week_start, Lesson.lesson_date <= week_end)
        .order_by(Lesson.lesson_date, Lesson.time_slot, Lesson.subgroup)
    ).all()


def get_all_groups_ordered(session) -> list[Group]:
    return session.scalars(select(Group).order_by(Group.source_name)).all()


def get_all_lessons(session) -> list[Lesson]:
    """All lessons in a deterministic order so in-memory bucketing by
    (group, week) / (group, date) matches the per-slice query orderings."""
    return session.scalars(
        select(Lesson).order_by(
            Lesson.group_id,
            Lesson.lesson_date,
            Lesson.time_slot,
            Lesson.subgroup,
        )
    ).all()


def get_all_subjects(session) -> list[Subject]:
    return session.scalars(select(Subject)).all()


def get_all_teachers(session) -> list[Teacher]:
    return session.scalars(select(Teacher)).all()


def get_all_rooms(session) -> list[Room]:
    return session.scalars(select(Room)).all()


def get_distinct_week_numbers(session) -> list[int | None]:
    return session.scalars(select(Lesson.week_number).distinct()).all()


def get_week_date_ranges(session) -> list[tuple[int, object, object]]:
    """(week_number, first_date, last_date) per week, ordered by week_number."""
    rows = session.execute(
        select(Lesson.week_number, func.min(Lesson.lesson_date), func.max(Lesson.lesson_date))
        .group_by(Lesson.week_number)
        .order_by(Lesson.week_number)
    ).all()
    return [(int(week), start, end) for week, start, end in rows if week is not None]


def get_distinct_lesson_dates(session) -> list:
    return session.scalars(select(Lesson.lesson_date).distinct()).all()


def get_latest_import_id(session) -> int | None:
    return session.scalar(select(Lesson.schedule_import_id).order_by(Lesson.schedule_import_id.desc()).limit(1))


def get_lesson_by_id(session, lesson_id: int) -> Lesson | None:
    return session.get(Lesson, lesson_id)


def get_room_by_id(session, room_id: int) -> Room | None:
    return session.get(Room, room_id)


def get_conflicting_lesson(session, *conditions, exclude_lesson_id: int | None) -> Lesson | None:
    query = select(Lesson).where(*conditions)
    if exclude_lesson_id is not None:
        query = query.where(Lesson.id != exclude_lesson_id)
    return session.scalar(query.limit(1))


def get_lesson_in_room_slot(
    session,
    *,
    room_id: int,
    lesson_date,
    time_slot: int,
    exclude_lesson_id: int | None,
) -> Lesson | None:
    query = select(Lesson).where(
        Lesson.room_id == room_id,
        Lesson.lesson_date == lesson_date,
        Lesson.time_slot == time_slot,
    )
    if exclude_lesson_id is not None:
        query = query.where(Lesson.id != exclude_lesson_id)
    return session.scalar(query.order_by(Lesson.subgroup, Lesson.id).limit(1))


def get_lessons_for_group_and_week(session, group_id: int, week_number: int) -> list[Lesson]:
    return session.scalars(
        select(Lesson)
        .where(Lesson.group_id == group_id, Lesson.week_number == week_number)
        .order_by(Lesson.lesson_date, Lesson.time_slot)
    ).all()


def get_lessons_for_teacher_and_week(session, teacher_id: int, week_number: int) -> list[Lesson]:
    return session.scalars(
        select(Lesson)
        .where(Lesson.teacher_id == teacher_id, Lesson.week_number == week_number)
        .order_by(Lesson.lesson_date, Lesson.time_slot)
    ).all()


def get_lessons_for_room_and_week(session, room_id: int, week_number: int) -> list[Lesson]:
    return session.scalars(
        select(Lesson)
        .where(Lesson.room_id == room_id, Lesson.week_number == week_number)
        .order_by(Lesson.lesson_date, Lesson.time_slot)
    ).all()


def get_teachers_ordered(session) -> list[Teacher]:
    return session.scalars(select(Teacher).order_by(Teacher.source_name)).all()


def get_rooms_ordered_all(session) -> list[Room]:
    return session.scalars(select(Room).order_by(Room.source_name)).all()


def get_lessons_for_group_and_date(session, group_id: int, lesson_date) -> list[Lesson]:
    return session.scalars(
        select(Lesson)
        .where(Lesson.group_id == group_id, Lesson.lesson_date == lesson_date)
        .order_by(Lesson.time_slot)
    ).all()


def get_group_by_id(session, group_id: int) -> Group | None:
    return session.get(Group, group_id)


def get_subject_by_id(session, subject_id: int) -> Subject | None:
    return session.get(Subject, subject_id)


def get_teacher_by_id(session, teacher_id: int) -> Teacher | None:
    return session.get(Teacher, teacher_id)


def get_lessons_with_teacher(session, *, lesson_date=None, time_slot: int | None = None) -> list[Lesson]:
    query = select(Lesson).where(Lesson.teacher_id.is_not(None))
    if lesson_date is not None:
        query = query.where(Lesson.lesson_date == lesson_date)
    if time_slot is not None:
        query = query.where(Lesson.time_slot == time_slot)
    return session.scalars(query.order_by(Lesson.lesson_date, Lesson.time_slot)).all()


def get_lessons_with_room(session, *, lesson_date=None, time_slot: int | None = None) -> list[Lesson]:
    query = select(Lesson).where(Lesson.room_id.is_not(None))
    if lesson_date is not None:
        query = query.where(Lesson.lesson_date == lesson_date)
    if time_slot is not None:
        query = query.where(Lesson.time_slot == time_slot)
    return session.scalars(query.order_by(Lesson.lesson_date, Lesson.time_slot)).all()


def find_group_by_name(session, name: str) -> Group | None:
    return session.scalar(select(Group).where(Group.source_name == name))


def find_subject_by_name(session, name: str) -> Subject | None:
    return session.scalar(select(Subject).where(Subject.source_name == name))


def find_teacher_by_source_id(session, source_teacher_id: str) -> Teacher | None:
    return session.scalar(select(Teacher).where(Teacher.source_teacher_id == source_teacher_id))


def find_room_by_name(session, name: str) -> Room | None:
    return session.scalar(select(Room).where(Room.source_name == name))
