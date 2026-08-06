# TEMPORARY dev seeding utility — safe to delete.
#
# Fills the DB with a full synthetic academic year by projecting the single
# base week already present (or 7.json if the DB is empty) onto every teaching
# week from 01.09.2025 to 30.06.2026, skipping the winter break. Every week is
# an identical grid with its own sequential week_number and correct dates.
#
# Run inside the api container (cwd is /workspace/apps/api):
#   docker compose exec -T api python scripts/seed_year.py --reset
#
# Flags:
#   --reset          required when the DB already has lessons; replaces them
#   --start YYYY-MM-DD / --end YYYY-MM-DD   override the academic-year bounds
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select

from app.core.cache import get_cache, init_cache
from app.core.config import get_database_url, get_redis_url
from app.db.engine import get_session_factory, init_engine
from app.models import Lesson, ScheduleImport
from app.services.import_schedule import import_schedule_from_json

# --- academic-year calendar (defaults) ---------------------------------------
DEFAULT_START = date(2025, 9, 1)
DEFAULT_END = date(2026, 6, 30)
# winter break: any Monday inside this inclusive range is skipped
WINTER_BREAK = (date(2025, 12, 29), date(2026, 1, 11))
# 7.json lives at the repo root, mounted at /workspace/7.json; cwd is apps/api
SEVEN_JSON_CANDIDATES = (Path("7.json"), Path("/workspace/7.json"), Path("../../7.json"))


@dataclass(frozen=True)
class LessonTemplate:
    group_id: int
    subject_id: int
    teacher_id: int | None
    room_id: int | None
    weekday: int
    time_slot: int
    start_time: time
    end_time: time
    subgroup: int
    lesson_type: str
    base_source_id: str


def find_seven_json() -> Path | None:
    for candidate in SEVEN_JSON_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def teaching_week_mondays(start: date, end: date, break_range: tuple[date, date]) -> list[date]:
    """Mondays of every teaching week in [start, end], skipping the break."""
    brk_start, brk_end = break_range
    monday = start - timedelta(days=start.weekday())
    mondays: list[date] = []
    while monday <= end:
        if monday >= start and not (brk_start <= monday <= brk_end):
            mondays.append(monday)
        monday += timedelta(days=7)
    return mondays


def load_template(session) -> list[LessonTemplate]:
    """Snapshot the earliest week's lessons as an in-memory template."""
    min_week = session.scalar(select(func.min(Lesson.week_number)))
    rows = session.scalars(select(Lesson).where(Lesson.week_number == min_week)).all()
    return [
        LessonTemplate(
            group_id=l.group_id,
            subject_id=l.subject_id,
            teacher_id=l.teacher_id,
            room_id=l.room_id,
            weekday=l.weekday,
            time_slot=l.time_slot,
            start_time=l.start_time,
            end_time=l.end_time,
            subgroup=l.subgroup,
            lesson_type=l.lesson_type,
            base_source_id=l.source_lesson_id,
        )
        for l in rows
    ]


def generate_year(session, mondays: list[date], template: list[LessonTemplate]) -> tuple[int, int]:
    """Wipe lesson data and project the template onto every teaching week."""
    session.execute(delete(Lesson))
    session.execute(delete(ScheduleImport))
    session.flush()

    group_count = len({t.group_id for t in template})
    total_lessons = 0
    lessons: list[Lesson] = []
    for week_number, monday in enumerate(mondays, start=1):
        imp = ScheduleImport(
            source_path=f"synthetic:seed_year:w{week_number}:{monday.isoformat()}",
            timetable_count=1,
            group_count=group_count,
            lesson_count=len(template),
            empty_day_count=0,
        )
        session.add(imp)
        session.flush()  # assign imp.id
        for t in template:
            lesson_date = monday + timedelta(days=t.weekday - 1)
            lessons.append(
                Lesson(
                    source_lesson_id=f"{t.base_source_id}:w{week_number}",
                    schedule_import_id=imp.id,
                    group_id=t.group_id,
                    subject_id=t.subject_id,
                    teacher_id=t.teacher_id,
                    room_id=t.room_id,
                    lesson_date=lesson_date,
                    start_time=t.start_time,
                    end_time=t.end_time,
                    weekday=t.weekday,
                    week_number=week_number,
                    time_slot=t.time_slot,
                    subgroup=t.subgroup,
                    lesson_type=t.lesson_type,
                )
            )
            total_lessons += 1
        if len(lessons) >= 5000:  # flush in batches to keep memory bounded
            session.bulk_save_objects(lessons)
            lessons.clear()
    if lessons:
        session.bulk_save_objects(lessons)
    return len(mondays), total_lessons


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed a full synthetic academic year (temporary dev tool).")
    p.add_argument("--reset", action="store_true", help="replace existing lesson data")
    p.add_argument("--start", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(), default=DEFAULT_START)
    p.add_argument("--end", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(), default=DEFAULT_END)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    init_engine(get_database_url())
    init_cache(get_redis_url())
    session_factory = get_session_factory()

    with session_factory() as session:
        existing = session.scalar(select(func.count()).select_from(Lesson)) or 0
        if existing and not args.reset:
            print(f"DB already has {existing} lessons. Re-run with --reset to replace them.", file=sys.stderr)
            return 1

        if not existing:
            seven = find_seven_json()
            if seven is None:
                print("DB is empty and 7.json not found — cannot build a template.", file=sys.stderr)
                return 1
            print(f"DB empty — importing base week from {seven} ...")
            import_schedule_from_json(seven)

        template = load_template(session)
        if not template:
            print("No template lessons found after loading base week.", file=sys.stderr)
            return 1

        mondays = teaching_week_mondays(args.start, args.end, WINTER_BREAK)
        weeks, lessons = generate_year(session, mondays, template)
        session.commit()

    get_cache().invalidate_all()

    print(
        f"Seeded {weeks} teaching weeks, {lessons} lessons "
        f"({len(template)} lessons/week × {weeks}) "
        f"from {mondays[0].isoformat()} to {(mondays[-1] + timedelta(days=5)).isoformat()}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
