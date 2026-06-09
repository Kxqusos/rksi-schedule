# Schedule RKS MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an MVP for college schedule management with JSON import, operator/admin editing, and PostgreSQL-backed persistence.

**Architecture:** Use a monorepo with `apps/web` on Next.js for the UI and `apps/api` on FastAPI for business logic, validation, and persistence. Treat `7.json` as the canonical import fixture, but normalize its shape during import so missing `lessons` arrays become empty days instead of errors.

**Tech Stack:** Next.js, FastAPI, PostgreSQL, SQLAlchemy or SQLModel, Alembic, Pydantic, Docker Compose.

---

### Task 1: Lock the repository skeleton and runtime wiring

**Files:**
- Create: `package.json`
- Create: `pnpm-workspace.yaml`
- Create: `pyproject.toml`
- Create: `docker-compose.yml`
- Create: `apps/web/package.json`
- Create: `apps/web/next.config.ts`
- Create: `apps/web/app/page.tsx`
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/app/main.py`
- Create: `apps/api/app/core/config.py`
- Create: `apps/api/app/db/session.py`
- Create: `apps/api/app/db/base.py`

- [ ] **Step 1: Write the minimum workspace manifests**

```json
{
  "name": "schedule-rks",
  "private": true,
  "packageManager": "pnpm@10.33.2",
  "scripts": {
    "web:dev": "pnpm --dir apps/web dev",
    "web:lint": "pnpm --dir apps/web lint",
    "web:typecheck": "pnpm --dir apps/web typecheck",
    "web:build": "pnpm --dir apps/web build"
  }
}
```

- [ ] **Step 2: Add FastAPI app entrypoint and config**

```python
from fastapi import FastAPI

app = FastAPI(title="Schedule RKS API")

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 3: Add Docker Compose for Postgres and local services**

```yaml
services:
  postgres:
    image: postgres:17
    environment:
      POSTGRES_DB: schedule_rks
      POSTGRES_USER: schedule_rks
      POSTGRES_PASSWORD: schedule_rks
    ports:
      - "5432:5432"
```

- [ ] **Step 4: Run the local smoke checks**

Run:
```bash
pnpm --dir apps/web dev
uv run --directory apps/api uvicorn app.main:app --reload
docker compose up -d postgres
```
Expected: web starts, API exposes `/health`, PostgreSQL starts cleanly.

- [ ] **Step 5: Commit the skeleton**

```bash
git add package.json pnpm-workspace.yaml pyproject.toml docker-compose.yml apps/web apps/api
git commit -m "chore: scaffold schedule rks workspace"
```

### Task 2: Define the import contract around `7.json`

**Files:**
- Create: `docs/import-format.md`
- Create: `apps/api/app/schemas/import_payload.py`
- Create: `apps/api/app/services/import_schedule/normalizer.py`
- Create: `apps/api/app/services/import_schedule/validator.py`
- Modify: `7.json`
- Create: `sample-data/schedule-import/7.json`

- [ ] **Step 1: Capture the observed payload shape**

Document the actual structure:
- root array with one object
- `timetable[]`
- `groups[]`
- `days[]`
- `lessons[]`
- nested `teachers[]` and `auditories[]`

- [ ] **Step 2: Normalize missing lesson arrays**

```python
def normalize_day(day: dict) -> dict:
    return {**day, "lessons": day.get("lessons", [])}
```

- [ ] **Step 3: Validate date and time fields**

Document required parsing rules:
- `date_start`, `date_end`, and lesson `date` use `DD-MM-YYYY`
- `time_start`, `time_end` use `HH:MM`
- `week_number`, `weekday`, `time`, `subgroup` are integers

- [ ] **Step 4: Promote the canonical sample into the sample-data folder**

Move the real sample to `sample-data/schedule-import/7.json` and keep the repository root file only if it is needed for compatibility.

- [ ] **Step 5: Commit the contract**

```bash
git add docs/import-format.md apps/api/app/schemas/import_payload.py apps/api/app/services/import_schedule/normalizer.py apps/api/app/services/import_schedule/validator.py sample-data/schedule-import/7.json 7.json
git commit -m "docs: define schedule import contract"
```

### Task 3: Model the schedule domain in PostgreSQL

**Files:**
- Create: `apps/api/app/models/user.py`
- Create: `apps/api/app/models/group.py`
- Create: `apps/api/app/models/teacher.py`
- Create: `apps/api/app/models/room.py`
- Create: `apps/api/app/models/subject.py`
- Create: `apps/api/app/models/lesson.py`
- Create: `apps/api/app/models/schedule_import.py`
- Create: `apps/api/app/models/audit_log.py`
- Create: `apps/api/app/models/enums.py`
- Create: `apps/api/app/db/migrations/0001_initial.sql`

- [ ] **Step 1: Define the core entities**

Minimum tables:
- users
- roles
- groups
- teachers
- rooms
- subjects
- lessons
- schedule_imports
- audit_log

- [ ] **Step 2: Encode uniqueness constraints**

Key constraints:
- one lesson per group/date/time/subgroup
- unique teacher identity by source `teacher_id`
- unique room by normalized name
- unique lesson source key by `Lesson_ID_Num`

- [ ] **Step 3: Add audit metadata**

Every mutable row stores:
- `created_at`
- `updated_at`
- `created_by`
- `updated_by`

- [ ] **Step 4: Add migration and seed entrypoints**

Provide the first SQL migration and a seed script for a default admin account.

- [ ] **Step 5: Run migration against local PostgreSQL**

Run:
```bash
docker compose up -d postgres
uv run alembic upgrade head
```
Expected: all tables exist and constraints apply.

### Task 4: Implement JSON import end to end

**Files:**
- Create: `apps/api/app/routers/imports.py`
- Create: `apps/api/app/services/import_schedule/service.py`
- Create: `apps/api/app/services/import_schedule/repository.py`
- Create: `apps/api/app/schemas/import_result.py`
- Create: `apps/api/tests/test_import_schedule.py`

- [ ] **Step 1: Write the failing import tests**

Cover:
- valid `7.json` imports successfully
- a day without `lessons` imports as an empty list
- duplicate `Lesson_ID_Num` is rejected
- invalid date format is rejected

- [ ] **Step 2: Implement the import service**

Import flow:
1. Parse payload
2. Normalize missing `lessons`
3. Upsert groups, teachers, rooms, subjects
4. Insert lessons idempotently
5. Record a `schedule_imports` row with counts and errors

- [ ] **Step 3: Expose the upload endpoint**

Add `POST /imports/schedule` that accepts a JSON file or raw JSON body and returns an import report.

- [ ] **Step 4: Run the import test suite**

Run:
```bash
pytest apps/api/tests/test_import_schedule.py -v
```
Expected: all import tests pass.

- [ ] **Step 5: Commit the import feature**

```bash
git add apps/api/app/routers/imports.py apps/api/app/services/import_schedule apps/api/app/schemas/import_result.py apps/api/tests/test_import_schedule.py
git commit -m "feat: import schedule from json"
```

### Task 5: Add operator/admin editing with role checks

**Files:**
- Create: `apps/api/app/routers/schedule.py`
- Create: `apps/api/app/services/schedule_editor/service.py`
- Create: `apps/api/app/services/auth/permissions.py`
- Create: `apps/api/app/schemas/schedule_edit.py`
- Create: `apps/web/app/(operator)/schedule/page.tsx`
- Create: `apps/web/app/(admin)/schedule/page.tsx`
- Create: `apps/web/app/(auth)/login/page.tsx`

- [ ] **Step 1: Write authorization tests**

Cover:
- operator can edit schedule items
- admin can edit schedule items and roles
- unauthorized users cannot mutate schedule

- [ ] **Step 2: Implement edit operations**

Support:
- create lesson
- update lesson
- delete lesson
- change teacher, room, subject, group, time, subgroup

- [ ] **Step 3: Add conflict checks**

Reject updates that collide on:
- same group and time slot
- same teacher and time slot
- same room and time slot

- [ ] **Step 4: Build the first UI screens**

Operator screen: browse and edit schedule.
Admin screen: broader access plus user/role management entry points.

- [ ] **Step 5: Run the full smoke test and commit**

Run:
```bash
pytest -q
pnpm web:build
```
Expected: backend tests pass, web build succeeds.
