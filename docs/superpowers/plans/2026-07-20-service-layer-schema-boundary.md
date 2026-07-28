# Service Layer Schema-Boundary Refactor Implementation Plan

**Status: implemented (2026-07-28).** All 8 tasks done. All 7 backend domains (rooms, groups, teachers, time_profiles, users, schedule_editor service + problems linter) now return domain objects; `mappers.py` is the sole `app.schemas` boundary and routers own the mapping call. Gate results: `grep -rl "app.schemas" apps/api/app/services/ | grep -v mappers.py` empty, full suite `65 passed`, `openapi.yaml` regenerated with no diff (API contract unchanged).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make the code actually satisfy the backend-layering plan's §2/§3 rule — `services/` never import or build Pydantic `schemas/`; `mappers.py` is the single place domain objects become response schemas, and routers own that mapping call.

**Architecture:** Today every `services/<domain>/service.py` both accepts Request DTOs as input types and returns Response schemas (it calls its own mapper). Invert it: services accept primitives / small `@dataclass` domain inputs and return ORM models or small domain `@dataclass`es; routers unpack the Request DTO, call the service, then call `mappers.*_to_response(...)` and `.model_dump(mode="json")`. Response JSON is byte-for-byte unchanged, so `openapi.yaml` and every existing endpoint test stay valid and act as the regression net.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2, pytest (SQLite test DBs), Docker Compose.

## Global Constraints

- Run backend tests inside the api container with DATABASE_URL unset:
  `docker compose exec -T api env -u DATABASE_URL /workspace/.venv/bin/pytest tests`
- Behavior-preserving refactor: **no** response body, status code, or route change. If any existing test needs editing, that is a red flag — stop and reconsider.
- After each task the whole suite must stay green (currently `65 passed`).
- No new schema imports in `services/**/service.py` or `services/**/problems.py`. The only files under `services/` allowed to import `app.schemas` are `mappers.py`.
- Keep existing code style; do not add relationship() or reorganize unrelated code.
- Small domain input carriers: if a create/update takes >2 domain fields, introduce a frozen `@dataclass` command in `service.py` (no schema import); otherwise pass primitives. Routers build the command / pass primitives from the Request DTO.
- Commit per task.

## Verification recipe (run at the end of every task)

```bash
# 1. domain tests green
docker compose exec -T api env -u DATABASE_URL /workspace/.venv/bin/pytest tests/test_<domain>.py -q
# 2. service no longer imports schemas
grep -n "app.schemas" apps/api/app/services/<domain>/service.py   # expect: no output
```

---

### Task 1: rooms

**Files:**
- Modify: `apps/api/app/services/rooms/service.py`
- Modify: `apps/api/app/services/rooms/mappers.py`
- Modify: `apps/api/app/routers/rooms.py`
- Test (existing, unchanged): `apps/api/tests/test_rooms.py`

**Interfaces:**
- Produces (new service signatures):
  - `list_rooms(session) -> list[tuple[Room, int]]`  (room, lesson_count)
  - `create_room(session, name: str, actor: Actor) -> Room`
  - `exclude_room(session, room_id: int, reason: str, actor: Actor) -> tuple[Room, int]`
  - `restore_room(session, room_id: int, actor: Actor) -> tuple[Room, int]`
  - `delete_room` unchanged (returns None)
- mappers gain: `room_to_response(room, lesson_count)` stays as-is (already takes domain input).

- [x] **Step 1: Confirm the regression net is green before touching anything**

Run: `docker compose exec -T api env -u DATABASE_URL /workspace/.venv/bin/pytest tests/test_rooms.py -q`
Expected: PASS (baseline).

- [x] **Step 2: Rewrite `rooms/service.py` to drop schema imports and return domain objects**

Remove `from app.schemas.room import ...`. New bodies (mapper calls deleted; return ORM/tuples):

```python
def list_rooms(session) -> list[tuple[Room, int]]:
    lesson_counts = repository.get_room_lesson_counts(session)
    rooms = repository.get_all_rooms(session)
    return [(room, int(lesson_counts.get(room.id, 0))) for room in rooms]


def create_room(session, name: str, actor: Actor) -> Room:
    name = name.strip()
    if not name:
        raise DuplicateRoomError(name)
    if repository.find_room_by_name(session, name) is not None:
        raise DuplicateRoomError(name)
    room = Room(source_name=name)
    session.add(room)
    session.flush()
    _audit(session, action="create", room=room, actor=actor, payload={"name": name})
    return room


def exclude_room(session, room_id: int, reason: str, actor: Actor) -> tuple[Room, int]:
    room = repository.get_room_by_id(session, room_id)
    if room is None:
        raise RoomNotFoundError()
    room.is_excluded = True
    room.exclusion_reason = reason.strip()
    session.flush()
    lesson_count = repository.get_room_lesson_count(session, room_id)
    _audit(session, action="exclude", room=room, actor=actor,
           payload={"name": room.source_name, "reason": room.exclusion_reason})
    return room, lesson_count


def restore_room(session, room_id: int, actor: Actor) -> tuple[Room, int]:
    room = repository.get_room_by_id(session, room_id)
    if room is None:
        raise RoomNotFoundError()
    previous_reason = room.exclusion_reason
    room.is_excluded = False
    room.exclusion_reason = ""
    session.flush()
    lesson_count = repository.get_room_lesson_count(session, room_id)
    _audit(session, action="restore", room=room, actor=actor,
           payload={"name": room.source_name, "previous_reason": previous_reason})
    return room, lesson_count
```

`delete_room` stays as-is. Note `create_room`'s empty-name guard now uses `name` (already stripped) in the error.

- [x] **Step 3: Update `routers/rooms.py` to unpack the request and call the mapper**

Add `from app.services.rooms import mappers`. Change bodies:

```python
@router.get("", response_model=list[RoomResponse])
def get_rooms(actor, session) -> list[dict]:
    return [mappers.room_to_response(room, count).model_dump(mode="json")
            for room, count in list_rooms(session)]

@router.post("", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
def post_room(payload: RoomCreateRequest, actor, session) -> dict:
    try:
        with session.begin():
            room = create_room(session, payload.name, actor)
    except DuplicateRoomError as exc:
        raise HTTPException(status_code=409, detail=f"room '{exc.name}' already exists") from exc
    return mappers.room_to_response(room, 0).model_dump(mode="json")

@router.post("/{room_id}/exclusion", response_model=RoomResponse)
def post_room_exclusion(room_id, payload: RoomExclusionRequest, actor, session) -> dict:
    try:
        with session.begin():
            room, count = exclude_room(session, room_id, payload.reason, actor)
    except RoomNotFoundError as exc:
        raise HTTPException(status_code=404, detail="room not found") from exc
    return mappers.room_to_response(room, count).model_dump(mode="json")

@router.delete("/{room_id}/exclusion", response_model=RoomResponse)
def delete_room_exclusion(room_id, actor, session) -> dict:
    try:
        with session.begin():
            room, count = restore_room(session, room_id, actor)
    except RoomNotFoundError as exc:
        raise HTTPException(status_code=404, detail="room not found") from exc
    return mappers.room_to_response(room, count).model_dump(mode="json")
```

(Keep the full existing `Annotated[...]` param signatures; only bodies/return-mapping shown here for brevity.)

- [x] **Step 4: Run the verification recipe**

Run both commands from "Verification recipe" with `<domain>=rooms`.
Expected: tests PASS; grep prints nothing.

- [x] **Step 5: Commit**

```bash
git add apps/api/app/services/rooms/service.py apps/api/app/routers/rooms.py
git commit -m "refactor(rooms): service returns domain objects, router owns mapping (layering §2/§3)"
```

---

### Task 2: groups

**Files:**
- Modify: `apps/api/app/services/groups/service.py`, `apps/api/app/services/groups/mappers.py` (only if it maps ORM already — verify), `apps/api/app/routers/groups.py`
- Test: `apps/api/tests/test_groups.py`

**Interfaces (new service signatures):**
- `list_groups(session) -> list[<domain>]` — return whatever ORM/aggregate `mappers.group_to_response` consumes (read `groups/mappers.py` first and mirror its input).
- `update_group(session, group_id: int, name: str | None, course: int | None, faculty: str | None, actor)` → return domain group aggregate. Read `GroupUpdateRequest` fields first and pass them as primitives; if >2 fields, add `@dataclass GroupUpdate` in service.py.
- `set_homeroom_teacher(session, group_id: int, teacher_id: int | None, actor)` → domain aggregate.
- `delete_group`, `clear_homeroom_teacher` unchanged (already schema-free).

- [x] **Step 1: Read `groups/mappers.py` and `schemas/group.py`** to learn the mapper's input shape and the two request DTOs' fields. Baseline test run.
- [x] **Step 2: Drop `from app.schemas.group import ...` from service.py**; change `update_group`/`set_homeroom_teacher` to take primitives (or a `@dataclass GroupUpdate`), and return the domain aggregate the mapper consumes instead of calling the mapper.
- [x] **Step 3: Update `routers/groups.py`** to unpack `payload` fields and call `mappers.group_to_response(...).model_dump(mode="json")`.
- [x] **Step 4: Run verification recipe (`<domain>=groups`).** Expected PASS + empty grep.
- [x] **Step 5: Commit** `refactor(groups): service returns domain objects, router owns mapping (layering §2/§3)`

---

### Task 3: teachers

**Files:** `apps/api/app/services/teachers/service.py`, `apps/api/app/routers/teachers.py`; test `apps/api/tests/test_teachers.py`.

**Interfaces (new service signatures):**
- `create_teacher(session, name: str, teacher_id: str, post: str, actor) -> Teacher`
- `create_teacher_absence(session, teacher_id: int, date_: date, all_day: bool, time_slot_start: int, time_slot_end: int, reason: str, actor) -> TeacherAbsence` — `TeacherAbsenceCreateRequest` has several fields; introduce `@dataclass AbsenceInput` in service.py and take that instead, built by the router.
- `list_teachers`, `list_available_teachers` → return the ORM/aggregate `teacher_to_response` consumes (read `teachers/mappers.py` first).
- Keep `teacher_absence_for_slot`, `teacher_absences_by_teacher`, `absence_matches_slot` (already schema-free, return ORM/dict).

- [x] **Step 1:** Read `teachers/mappers.py` + `schemas/teacher.py`. Baseline test run.
- [x] **Step 2:** Drop schema import; add `@dataclass AbsenceInput`; services return ORM/aggregates, not responses.
- [x] **Step 3:** Router unpacks `TeacherCreateRequest`/`TeacherAbsenceCreateRequest` into primitives/`AbsenceInput` and calls `mappers.*` for responses.
- [x] **Step 4:** Verification recipe (`teachers`). Expected PASS + empty grep.
- [x] **Step 5:** Commit `refactor(teachers): service returns domain objects, router owns mapping (layering §2/§3)`

---

### Task 4: time_profiles

**Files:** `apps/api/app/services/time_profiles/service.py`, `apps/api/app/routers/time_profiles.py`; test `apps/api/tests/test_time_profiles.py`.

`DayTimeProfileCreateRequest`/`WeekTimeProfileCreateRequest` carry nested slot/day lists — introduce `@dataclass DayProfileInput`/`WeekProfileInput` (with plain nested dataclasses or lists of tuples) in service.py; the router converts the Request DTO into them. Services return ORM `DayTimeProfile`/`WeekTimeProfile` (+ any aggregate the mapper needs).

- [x] **Step 1:** Read `time_profiles/mappers.py` + `schemas/time_profile.py`. Baseline test run.
- [x] **Step 2:** Drop schema import; add input dataclasses; `create_*`/`update_*` accept them and return ORM; delete mapper calls from service.
- [x] **Step 3:** Router builds input dataclasses from payload, calls `mappers.*_to_response(...).model_dump(mode="json")`.
- [x] **Step 4:** Verification recipe (`time_profiles`). Expected PASS + empty grep.
- [x] **Step 5:** Commit `refactor(time_profiles): service returns domain objects, router owns mapping (layering §2/§3)`

---

### Task 5: users

**Files:** `apps/api/app/services/users/service.py`, `apps/api/app/routers/users.py`, `apps/api/app/services/auth/permissions.py` (imports `get_user_by_id` — return type unchanged, no edit expected); test `apps/api/tests/test_auth_users.py`.

**Interfaces:**
- `create_user(session, username: str, display_name: str, password: str, role: str, actor) -> User` (introduce `@dataclass NewUser` since 4 fields).
- `list_users`, `get_user_credentials` → return ORM/aggregate the mapper consumes.
- `authenticate_user`, `get_user_by_id`, `revoke_user`, `change_user_password` already schema-free — leave; confirm they return ORM `User`, not a response.

- [x] **Step 1:** Read `users/mappers.py` + `schemas/user.py`. Baseline test run. Note `auth/routers` also call `get_user_by_id`/`authenticate_user` — verify their return types don't change.
- [x] **Step 2:** Drop `from app.schemas.user import UserCreateRequest`; add `@dataclass NewUser`; `create_user` takes it and returns `User`.
- [x] **Step 3:** Router (`routers/users.py`) unpacks `UserCreateRequest` → `NewUser`, calls `mappers.user_to_response(...)`. Check `routers/auth.py` still maps correctly (it builds `LoginResponse`/`UserResponse` — those already live in the router, fine).
- [x] **Step 4:** Verification recipe (`users`) plus `pytest tests/test_auth_users.py -q`. Expected PASS + empty grep.
- [x] **Step 5:** Commit `refactor(users): service returns domain objects, router owns mapping (layering §2/§3)`

---

### Task 6: schedule_editor — public schedule + lesson mutations

**Files:** `apps/api/app/services/schedule_editor/service.py`, `apps/api/app/services/schedule_editor/mappers.py`, `apps/api/app/routers/schedule.py`; tests `apps/api/tests/test_schedule_editor.py`.

This service builds `PublicScheduleWeekResponse`, `PublicScheduleIndexResponse`, `LessonResponse`, `ScheduleSlotRoomResponse` directly and takes `LessonCreateRequest`/`LessonUpdateRequest`. Move all response construction into `schedule_editor/mappers.py`; introduce domain dataclasses.

**Interfaces (new/changed):**
- Introduce in `service.py` (schema-free) domain dataclasses:
  - `@dataclass PublicWeek` (weekday→day rows of plain fields), `@dataclass PublicIndex` (entities), `@dataclass SlotRoom`, and reuse existing `LessonMutationResult` (already a dataclass) — but ensure its `.lesson` field becomes a domain object, not `LessonResponse`.
- Service functions return those dataclasses:
  - `get_latest_public_week(session) -> PublicWeek`
  - `get_public_schedule_index(session) -> PublicIndex`
  - `get_public_week_for_entity(...) -> PublicWeek`
  - `list_lessons_by_slot(...) -> list[SlotRoom]`
  - `create_lesson`/`update_lesson`/`delete_lesson` take primitives / a `@dataclass LessonWrite` (from the Request DTO) and return domain results carrying cache_keys + domain lesson + domain warnings.
- `mappers.py` gains `public_week_to_response`, `public_index_to_response`, `slot_room_to_response`, `lesson_result_to_response`, `problem_to_response` (see Task 7).

- [x] **Step 1:** Read `schedule_editor/service.py` fully and `schemas/schedule_edit.py`. Baseline: `pytest tests/test_schedule_editor.py -q`.
- [x] **Step 2:** Add domain dataclasses to `service.py`; convert the public-week/index/slot builders and `_lesson_response` to return domain dataclasses (no schema import for these paths). Move field-shaping into `mappers.py`.
- [x] **Step 3:** Add mapper functions in `mappers.py` that turn the domain dataclasses into the existing response schemas (identical field values).
- [x] **Step 4:** Convert `create_lesson`/`update_lesson`/`delete_lesson` inputs to `@dataclass LessonWrite`; router builds it from `LessonCreateRequest`/`LessonUpdateRequest`.
- [x] **Step 5:** Update `routers/schedule.py`: unpack requests, call `mappers.*` for every response, keep cache invalidation exactly as-is.
- [x] **Step 6:** Verification: `pytest tests/test_schedule_editor.py -q` PASS; `grep -n app.schemas apps/api/app/services/schedule_editor/service.py` empty.
- [x] **Step 7:** Commit `refactor(schedule_editor): domain objects for public/mutation paths, mappers own responses (layering §2/§3)`

---

### Task 7: schedule_editor — problems linter

**Files:** `apps/api/app/services/schedule_editor/problems.py`, `apps/api/app/services/schedule_editor/mappers.py`, `apps/api/app/routers/schedule.py`; tests `apps/api/tests/test_schedule_editor.py`.

`problems.py` uses `ScheduleProblemResponse` as its working type across ~20 helpers. Introduce a domain `@dataclass ScheduleProblem` with the same fields; every helper produces/consumes `ScheduleProblem`; the public entry point returns `list[ScheduleProblem]`; the router maps with `mappers.problem_to_response`.

**Interfaces:**
- `service.py`/`problems.py` gain `@dataclass ScheduleProblem` (fields identical to `ScheduleProblemResponse`).
- `list_schedule_problems(session) -> list[ScheduleProblem]`
- All `_*_errors`/`_*_warnings`/aggregation helpers switch their `ScheduleProblemResponse` type to `ScheduleProblem`.
- `mappers.problem_to_response(ScheduleProblem) -> ScheduleProblemResponse`.
- `_warnings_for_lesson` feeds Task 6's `LessonMutationResult.warnings` — keep it returning `ScheduleProblem`; the lesson-result mapper maps each warning.

- [x] **Step 1:** Baseline `pytest tests/test_schedule_editor.py -q`. Read `problems.py` fully.
- [x] **Step 2:** Define `@dataclass ScheduleProblem`; mechanically replace `ScheduleProblemResponse(` construction with `ScheduleProblem(` and the type annotations throughout `problems.py`; drop `from app.schemas...` from `problems.py`.
- [x] **Step 3:** Add `mappers.problem_to_response`; router `get_problems` maps `list_schedule_problems` output; the lesson-mutation mapper (Task 6) maps `warnings`.
- [x] **Step 4:** Verification: `pytest tests/test_schedule_editor.py -q` PASS; `grep -n app.schemas apps/api/app/services/schedule_editor/problems.py` empty.
- [x] **Step 5:** Commit `refactor(schedule_editor): domain ScheduleProblem, mapper builds response (layering §2/§3)`

---

### Task 8: whole-suite gate, contract check, plan status

**Files:** `openapi.yaml` (regenerate — expect no diff), `docs/architecture/backend-layering-refactor.md`.

- [x] **Step 1:** Full suite: `docker compose exec -T api env -u DATABASE_URL /workspace/.venv/bin/pytest tests -q`. Expected `65 passed`.
- [x] **Step 2:** Global invariant — no service builds/imports schemas:
  `grep -rn "app.schemas" apps/api/app/services/ | grep -v "/mappers.py:"`
  Expected: no output.
- [x] **Step 3:** Regenerate `openapi.yaml` with the documented command; `git diff --stat openapi.yaml` should be empty (responses unchanged). If it differs, a response shape drifted — investigate before committing.
- [x] **Step 4:** Update the status line of `docs/architecture/backend-layering-refactor.md` to state §2/§3 (services schema-free, mappers as sole boundary) is now actually enforced across all domains, with today's date.
- [x] **Step 5:** Commit `docs: record service-layer schema boundary now enforced (layering §2/§3)`
