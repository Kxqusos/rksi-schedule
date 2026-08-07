# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

MVP сервиса расписания занятий колледжа: админка для импорта/редактирования расписания, публичный просмотр расписания, управление пользователями, группами, преподавателями, кабинетами, профилями времени и линтер проблем расписания.

Stack: Next.js 15 / React 19 / TypeScript (frontend) + FastAPI / Pydantic v2 / SQLAlchemy 2 / Alembic (backend) + PostgreSQL 17. Frontend tooling is `pnpm`; backend uses `uv`/Python 3.12 inside the API Docker image.

## Dev environment

Runs via Docker Compose:

```bash
docker compose up --build   # first run
docker compose up           # subsequent runs
```

- `postgres`: `localhost:5432`, db `schedule_rks`, user `schedule_rks`
- `api`: FastAPI at `http://127.0.0.1:8001` (runs `alembic upgrade head` then `uvicorn --reload`)
- `web`: Next.js at `http://127.0.0.1:3003`

Bind volumes + watch are configured, so most changes don't require a rebuild.

## Commands

Backend tests (must run with `DATABASE_URL` unset so tests use their own SQLite db, not the compose Postgres):

```bash
docker compose exec -T api env -u DATABASE_URL /workspace/.venv/bin/pytest tests
docker compose exec -T api env -u DATABASE_URL /workspace/.venv/bin/pytest tests/test_schedule_editor.py -k some_test  # single test
```

Frontend typecheck:

```bash
pnpm web:typecheck
```

Migrations:

```bash
docker compose exec -T api alembic current        # check current revision
docker compose exec -T api alembic upgrade head    # apply
```

## OpenAPI

`openapi.yaml` at repo root is the source of truth for the API contract. Whenever endpoints, request/response schemas, or auth requirements change, regenerate it:

```bash
docker compose exec -T api python - <<'PY' | ruby -ryaml -rjson -e 'puts YAML.dump(JSON.parse(STDIN.read)).sub(/^---\n/, "")' > openapi.yaml
from app.main import app
import json
print(json.dumps(app.openapi(), ensure_ascii=False))
PY
```

After generating, verify affected endpoints with `rg`.

## Architecture

Backend (`apps/api/app/`):
- `main.py` — assembles the FastAPI app and wires up routers.
- `models.py` — all SQLAlchemy models.
- `routers/` — thin HTTP layer only (auth, session, HTTP error translation, calling into services). No business logic here.
- `services/` — all business logic, organized per domain (`schedule_editor/`, `import_schedule/`, `teachers.py`, `groups.py`, `rooms.py`, `time_profiles.py`, `users.py`, `auth/`, `bootstrap.py`).
- `schemas/` — Pydantic request/response models, one file per domain.
- `alembic/versions/` — DB migrations; every schema change needs one.

Two key service modules carry the actual domain rules and are the most important to read before touching scheduling behavior:
- `services/schedule_editor/service.py` — schedule mutation rules and the problem/issue linter.
- `services/import_schedule/service.py` — import of schedule from JSON (`7.json` at repo root is the fixed source import file).

Frontend (`apps/web/app/`):
- `page.tsx` — main admin SPA (sidebar-driven, not a landing page — first screen must be a working interface).
- `viewer/page.tsx` — public read-only schedule view.
- `globals.css` — global styles; breakpoints: widescreen ≥2400px, desktop default, laptop ≤1366px, tablet landscape ≤1200px, tablet portrait ≤1024px, mobile landscape ≤880px, mobile portrait ≤767px.

## Domain rules (schedule semantics)

- Import from `7.json` is not blocked by linter rules.
- `Классный час` is inserted Monday, period 4; later Monday classes (after period 3) shift accordingly.
- If a group has 0 periods on Monday, no `Классный час` is created for that day.
- `Классный час` and `Доп занятия` do not count toward the 18-periods/week limit or daily group limits.
- A foreign-language class split into two subgroups is not a violation of the "2 teachers for 1 group in 1 period" rule (`_is_foreign_language_subgroup_split` in `schedule_editor/service.py` only forgives subjects whose name contains "иностран" — a non-language subject split the same way (2 subgroups, 2 teachers, 1 period) is saved correctly but is currently flagged as `group_slot_multiple_teachers` `error`; known mislabeling, not a data-loss bug).
- "2 groups for 1 teacher" and "2 groups for 1 room" at the same period are allowed and preserved as separate `Lesson` rows (different `group_id`, same `teacher_id`/`room_id`); surfaced only as `warning` (`teacher_double_booked`/`room_double_booked`), never blocking.
- Import (`import_schedule/service.py`) never applies linter rules, so all of the above combinations are written to the DB as-is regardless of severity; problems only surface afterward via `/schedule/problems`.
- One real import-time data-loss case: if a single JSON lesson entry's `teachers`/`auditories` array has more than one element, only `teachers[0]`/`auditories[0]` is kept — the rest is silently dropped (`_get_or_create_teacher`/`_get_or_create_room`). Not observed in `7.json` to date (every entry has 0 or 1 teacher/room); multiple teachers/rooms for one lesson are represented in source data as separate top-level lesson entries (e.g. subgroup splits) instead, which import handles correctly.
- In "Проблемы" (issues), group-level problems are aggregated: one notification per problem class, one row per group inside it.
- For schedule substitutions, warnings don't block the action; hard errors do. The exception is `NON_BLOCKING_EDIT_CODES` in `schedule_editor/problems.py`: errors no single edit can avoid. `group_day_minimum_not_met` is there because the daily minimum is 2 pairs, so the first lesson of any day is always below it — enforcing it on one mutation made the state unreachable. Such codes are returned in the mutation's `warnings` and still listed by the linter.
- Role model: operator can edit schedule, rooms, teachers, groups; admin can additionally manage users.
- Schedule JSON import (`POST /imports/schedule`, `routers/imports.py`) requires an operator/admin bearer token (`require_editor_actor`); it is not an open endpoint.

## Conventions

- Visible/user-facing dates: `DD.MM.YYYY`. API JSON date fields stay ISO (`YYYY-MM-DD`).
- New scheduling-rule changes need regression tests in `apps/api/tests/test_schedule_editor.py`.
- Don't add explanatory in-app copy for self-evident UI; use existing CSS classes/patterns and `lucide-react` icons for new admin UI.
- Bootstrap admin credentials come from `.env` (`ADMIN_USERNAME`, `ADMIN_DISPLAY_NAME`, `ADMIN_PASSWORD`) — never hardcode real credentials in code or tests outside fixtures.
- Avoid broad refactors mixed into functional changes; keep existing code structure/style.
