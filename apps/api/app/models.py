from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("name", name="uq_roles_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username", name="uq_users_username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ScheduleImport(Base):
    __tablename__ = "schedule_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_path: Mapped[str] = mapped_column(String(500), nullable=False)
    timetable_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    group_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lesson_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    empty_day_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("source_name", name="uq_groups_source_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    course: Mapped[int] = mapped_column(Integer, nullable=False)
    faculty: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    homeroom_teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True)


class Teacher(Base):
    __tablename__ = "teachers"
    __table_args__ = (UniqueConstraint("source_teacher_id", name="uq_teachers_source_teacher_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_teacher_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    post: Mapped[str] = mapped_column(String(200), nullable=False, default="")


class TeacherAbsence(Base):
    __tablename__ = "teacher_absences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=False)
    absence_date: Mapped[date] = mapped_column(Date, nullable=False)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    time_slot_start: Mapped[int] = mapped_column(Integer, nullable=False)
    time_slot_end: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (UniqueConstraint("source_name", name="uq_rooms_source_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exclusion_reason: Mapped[str] = mapped_column(String(300), nullable=False, default="")


class DayTimeProfile(Base):
    __tablename__ = "day_time_profiles"
    __table_args__ = (UniqueConstraint("name", name="uq_day_time_profiles_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DayTimeProfileSlot(Base):
    __tablename__ = "day_time_profile_slots"
    __table_args__ = (UniqueConstraint("day_profile_id", "slot_number", name="uq_day_time_profile_slots_profile_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day_profile_id: Mapped[int] = mapped_column(ForeignKey("day_time_profiles.id"), nullable=False)
    slot_number: Mapped[int] = mapped_column(Integer, nullable=False)
    time_start: Mapped[time] = mapped_column(nullable=False)
    time_end: Mapped[time] = mapped_column(nullable=False)


class WeekTimeProfile(Base):
    __tablename__ = "week_time_profiles"
    __table_args__ = (UniqueConstraint("name", name="uq_week_time_profiles_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WeekTimeProfileDay(Base):
    __tablename__ = "week_time_profile_days"
    __table_args__ = (UniqueConstraint("week_profile_id", "weekday", name="uq_week_time_profile_days_profile_weekday"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_profile_id: Mapped[int] = mapped_column(ForeignKey("week_time_profiles.id"), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    day_profile_id: Mapped[int] = mapped_column(ForeignKey("day_time_profiles.id"), nullable=False)


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("source_name", name="uq_subjects_source_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(250), nullable=False)


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (
        UniqueConstraint("source_lesson_id", name="uq_lessons_source_lesson_id"),
        UniqueConstraint(
            "group_id",
            "lesson_date",
            "time_slot",
            "subgroup",
            name="uq_lessons_group_date_time_subgroup",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_lesson_id: Mapped[str] = mapped_column(String(100), nullable=False)
    schedule_import_id: Mapped[int] = mapped_column(ForeignKey("schedule_imports.id"), nullable=False)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    lesson_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(nullable=False)
    end_time: Mapped[time] = mapped_column(nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    time_slot: Mapped[int] = mapped_column(Integer, nullable=False)
    subgroup: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lesson_type: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
