# AGENTS.md

Инструкции для агентов и разработчиков, которые продолжают работу в этом репозитории.

## Проект

MVP сервиса расписания занятий колледжа. Есть админская часть для импорта и редактирования расписания, публичный просмотр расписания, управление пользователями, группами, преподавателями, кабинетами, профилями времени и линтером проблем расписания.

## Стек

- Frontend: Next.js 15, React 19, TypeScript, `lucide-react`, глобальные стили в `apps/web/app/globals.css`.
- Backend API: FastAPI, Pydantic v2, SQLAlchemy 2, Alembic.
- Database: PostgreSQL 17.
- Tooling: `pnpm` для frontend, Python/uv окружение внутри API Docker image.
- API schema: актуальная OpenAPI-схема лежит в `openapi.yaml` в корне репозитория.

## Dev-Окружение

Проект запущен и рассчитан на работу в Docker Compose dev-режиме.

Сервисы:

- `postgres`: `localhost:5432`, база `schedule_rks`, пользователь `schedule_rks`.
- `api`: FastAPI на `http://127.0.0.1:8001`.
- `web`: Next.js на `http://127.0.0.1:3003`.

Запуск:

```bash
docker compose up --build
```

После первого билда обычно достаточно:

```bash
docker compose up
```

API контейнер перед стартом выполняет `alembic upgrade head`, затем запускает `uvicorn` с reload. В compose подключены bind volumes и watch-настройки, поэтому для большинства изменений не нужно пересобирать контейнеры.

## Важные Файлы

- `7.json` - фиксированный исходный JSON расписания для импорта.
- `openapi.yaml` - актуальная документация API.
- `docker-compose.yml` - dev-инфраструктура.
- `apps/api/app/main.py` - сборка FastAPI приложения и подключение роутеров.
- `apps/api/app/models.py` - SQLAlchemy модели.
- `apps/api/alembic/versions/` - миграции БД.
- `apps/api/app/services/` - бизнес-логика API.
- `apps/api/app/routers/` - FastAPI endpoints.
- `apps/api/tests/` - backend tests.
- `apps/web/app/page.tsx` - основная админская SPA-страница.
- `apps/web/app/viewer/page.tsx` - публичный просмотр расписания.
- `apps/web/app/globals.css` - стили frontend.

## Проверки

Backend tests запускать из API контейнера так, чтобы тестовые SQLite БД не подменялись compose `DATABASE_URL`:

```bash
docker compose exec -T api env -u DATABASE_URL /workspace/.venv/bin/pytest tests
```

Frontend typecheck:

```bash
pnpm web:typecheck
```

Проверить текущую миграцию dev-БД:

```bash
docker compose exec -T api alembic current
```

Применить миграции вручную:

```bash
docker compose exec -T api alembic upgrade head
```

## OpenAPI

Если меняются endpoints, request/response schema или auth requirements, обновить `openapi.yaml`.

Генерация из живого FastAPI приложения без добавления Python-зависимостей:

```bash
docker compose exec -T api python - <<'PY' | ruby -ryaml -rjson -e 'puts YAML.dump(JSON.parse(STDIN.read)).sub(/^---\n/, "")' > openapi.yaml
from app.main import app
import json
print(json.dumps(app.openapi(), ensure_ascii=False))
PY
```

После генерации проверить нужные endpoints через `rg`.

## Code Style

Общее:

- Сохранять существующую структуру и стиль кода.
- Не делать широкие рефакторинги вместе с функциональными правками.
- Для поиска использовать `rg`.
- Для ручных изменений файлов использовать `apply_patch`.
- Не откатывать чужие изменения в рабочем дереве.
- Видимые пользователю даты форматировать как `DD.MM.YYYY`. API JSON-поля дат оставлять ISO (`YYYY-MM-DD`) для машинного обмена.

Backend:

- Бизнес-логику держать в `apps/api/app/services/`.
- Роутеры должны быть тонкими: auth, session, HTTP ошибки, вызов service layer.
- Pydantic schemas держать в `apps/api/app/schemas/`.
- Новые изменения БД оформлять Alembic migration в `apps/api/alembic/versions/`.
- Проверки расписания и линтер проблем находятся в `apps/api/app/services/schedule_editor/service.py`.
- Импорт расписания из JSON находится в `apps/api/app/services/import_schedule/service.py`.
- При изменении правил расписания добавлять regression tests в `apps/api/tests/test_schedule_editor.py`.

Frontend:

- Не превращать админку в landing page. Первый экран должен быть рабочим интерфейсом.
- Sidebar используется как основная навигация админки.
- Для кнопок и действий использовать существующие CSS-классы и паттерны.
- Иконки брать из `lucide-react`.
- Не добавлять объясняющий in-app текст про очевидную функциональность.
- Видимые даты форматировать как `DD.MM.YYYY`.

Breakpoints:

- Widescreen: `min-width: 2400px`
- Desktop: default
- Laptop: `max-width: 1366px`
- Tablet Landscape: `max-width: 1200px`
- Tablet Portrait: `max-width: 1024px`
- Mobile Landscape: `max-width: 880px`
- Mobile Portrait: `max-width: 767px`

## Domain Rules

- Импорт из `7.json` не блокируется правилами линтера.
- `Классный час` добавляется на понедельник 4-й парой; занятия после 3-й пары в понедельник сдвигаются.
- Если у группы в понедельник 0 пар, `Классный час` для этого дня не создается.
- `Классный час` не считается в лимит 18 пар в неделю и дневные лимиты группы.
- `Доп занятия` не считаются в лимит 18 пар в неделю и дневные лимиты группы.
- Иностранный язык с двумя подгруппами не считается нарушением "2 преподавателя на 1 группу в 1 пару" (`_is_foreign_language_subgroup_split` в `schedule_editor/service.py` прощает только предметы, где в названии встречается "иностран" — не-языковой предмет с такой же структурой (2 подгруппы, 2 преподавателя, 1 пара) сохраняется корректно, но ошибочно помечается как `error` `group_slot_multiple_teachers`; это известная неточность классификации, не потеря данных).
- "2 группы на 1 преподавателя" и "2 группы на 1 кабинет" в одну пару — допустимы и сохраняются как отдельные строки `Lesson` (разный `group_id`, одинаковый `teacher_id`/`room_id`); линтер показывает это только как `warning` (`teacher_double_booked`/`room_double_booked`), без блокировки.
- Импорт (`import_schedule/service.py`) не применяет правила линтера вообще, поэтому все перечисленные комбинации пишутся в БД как есть независимо от severity; проблемы видны только постфактум через `/schedule/problems`.
- Единственный реальный случай потери данных при импорте: если в одной JSON-записи занятия массив `teachers`/`auditories` содержит больше одного элемента, берётся только `teachers[0]`/`auditories[0]`, остальное отбрасывается без следа (`_get_or_create_teacher`/`_get_or_create_room`). На данных `7.json` такого не встречается (везде 0 или 1 преподаватель/кабинет на запись); несколько преподавателей/кабинетов на одну пару у группы представлены в исходных данных отдельными top-level записями занятий (например, разбивка на подгруппы), и это импорт обрабатывает корректно.
- В разделе "Проблемы" групповые проблемы агрегируются: один класс проблемы - одно уведомление, внутри `1 группа = 1 строка`.
- Для замен расписания предупреждения не блокируют действие, жесткие ошибки блокируют. Исключение — `NON_BLOCKING_EDIT_CODES` в `schedule_editor/problems.py`: ошибки, которых не может избежать ни одна отдельная правка. Туда входит `group_day_minimum_not_met`, потому что минимум в дне — 2 пары, и первое занятие любого дня всегда ниже минимума; блокировка делала это состояние недостижимым. Такие коды возвращаются в `warnings` мутации и по-прежнему видны в линтере.
- Оператор может изменять расписание, управлять кабинетами, преподавателями и группами.
- Администратор может управлять пользователями.
- JSON-импорт расписания (`POST /imports/schedule`, `routers/imports.py`) требует bearer-токен роли operator/admin (`require_editor_actor`) — это не открытый эндпоинт.

## Auth

Bootstrap admin берется из `.env`:

- `ADMIN_USERNAME`
- `ADMIN_DISPLAY_NAME`
- `ADMIN_PASSWORD`

Не хардкодить реальные креды в коде или тестах вне test fixtures.

## Git

Рабочее дерево может быть грязным. Перед правками смотрите `git status --short`, но не откатывайте изменения, которые не относятся к текущей задаче.

Коммиты и push делать только если пользователь прямо попросил.
