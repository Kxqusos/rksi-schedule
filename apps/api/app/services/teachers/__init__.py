from app.services.teachers.service import (
    DuplicateTeacherError,
    TeacherAbsenceNotFoundError,
    TeacherNotFoundError,
    absence_matches_slot,
    create_teacher,
    create_teacher_absence,
    delete_teacher,
    delete_teacher_absence,
    list_available_teachers,
    list_teachers,
    teacher_absence_for_slot,
    teacher_absences_by_teacher,
)

__all__ = [
    "DuplicateTeacherError",
    "TeacherAbsenceNotFoundError",
    "TeacherNotFoundError",
    "absence_matches_slot",
    "create_teacher",
    "create_teacher_absence",
    "delete_teacher",
    "delete_teacher_absence",
    "list_available_teachers",
    "list_teachers",
    "teacher_absence_for_slot",
    "teacher_absences_by_teacher",
]
