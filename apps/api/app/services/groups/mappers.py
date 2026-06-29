from __future__ import annotations

from app.models import Group, Teacher
from app.schemas.group import GroupResponse


def group_to_response(group: Group, lesson_count: int, teacher: Teacher | None) -> GroupResponse:
    return GroupResponse(
        id=group.id,
        name=group.source_name,
        course=group.course,
        faculty=group.faculty,
        lesson_count=lesson_count,
        homeroom_teacher_id=teacher.id if teacher else None,
        homeroom_teacher_name=teacher.source_name if teacher else None,
    )
