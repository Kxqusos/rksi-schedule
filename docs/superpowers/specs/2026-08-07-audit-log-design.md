# Раздел «История изменений» — дизайн

Дата: 2026-08-07

## Задача

Дать администраторам и операторам просматриваемый журнал изменений: что произошло,
когда и кто это сделал, с текстовым поиском.

## Исходное состояние

Таблица `audit_log` (`models.py:165`) уже существует и наполняется — 25 вызовов `_audit`
из шести сервисов (`rooms`, `groups`, `teachers`, `time_profiles`, `users`,
`schedule_editor`). Колонки: `entity_type`, `entity_id`, `action`, `actor_role`,
`actor_name`, `payload` (JSON), `created_at`.

Читающего кода нет вообще: ни роутера, ни схемы, ни репозитория; в `openapi.yaml`
слово `audit` не встречается. Раздел «История изменений» присутствует в сайдбаре
(`apps/web/app/page.tsx:20`), но отсутствует в цепочке рендера секций (`:182`), поэтому
открывается заглушкой «Раздел в разработке».

Пароли и токены в `payload` не попадают ни в одном из шести сервисов — проверено
построчно. Персональные данные ограничены `username`, `display_name`, ФИО
преподавателей и свободным текстом `reason` у отсутствий.

Работа делится на три части: чтение (основное), обогащение payload (без него
человекочитаемые фразы не собираются) и две дыры в записи.

## Решения

| Вопрос | Решение |
|---|---|
| Доступ | `require_editor_actor` — оператор и админ |
| Поиск | Строка поиска + чипы по разделам + период |
| Фильтр по действию | Не нужен: русские слова действий ловит текстовый поиск |
| Отображение правки | Только человекочитаемая фраза, сырой JSON не показываем |
| Пагинация | offset/limit, батч 100, кнопка «Показать ещё» |
| Пробелы записи | Закрываем импорт расписания и снятие классрука; входы в систему не логируем |
| Размещение UI | Отдельный файл `apps/web/app/audit-page.tsx` |

## Backend

### Новый домен `services/audit/`

Структура повторяет остальные домены проекта.

**`repository.py`** — один запрос с фильтрами, `ORDER BY created_at DESC, id DESC`,
плюс параллельный `count()` для `total`.

**`mappers.py`** — `audit_entry_to_response(entry)`: собирает фразу из `entity_type`,
`action` и `payload` по каталогу ниже.

**`service.py`** — `list_audit_entries(session, *, query, entity_types, date_from,
date_to, limit, offset) -> AuditPage`. Только чтение, транзакция не открывается.

### Роутер `routers/audit.py`

`GET /audit`, `require_editor_actor`. Параметры запроса:

| Параметр | Тип | По умолчанию |
|---|---|---|
| `q` | `str \| None` | — |
| `entity_type` | повторяемый `str` | все |
| `date_from`, `date_to` | `date \| None` | — |
| `limit` | `int`, 1..200 | 100 |
| `offset` | `int`, ≥0 | 0 |

`date_to` включает весь указанный день (сравнение по `< date_to + 1 день`).

Первый эндпоинт проекта с `fastapi.Query` и пагинацией — образца для переиспользования
в репозитории нет.

### Схемы `schemas/audit.py`

```
AuditEntryResponse:  id, created_at, actor_name, actor_role, actor_role_label,
                     entity_type, entity_label, action, summary
AuditPageResponse:   items, total, limit, offset
```

`summary` формирует backend — фраза тестируется в pytest, фронтенд остаётся тонким.

### Текстовый поиск

`ILIKE` по `actor_name` и по `payload`, приведённому к тексту: ловит «305», «Иванов»,
«ИС-21» — то, что реально лежит в JSON.

Отдельно решается проблема слов, которые пользователь видит на экране, но которых нет
в БД. Поисковый запрос сверяется со словарём русских лейблов `entity_type` и `action`;
совпавшие ключи подмешиваются в тот же SQL через `OR`. Так «удал» находит все записи
с `action` из {`delete`, `revoke`}, а «кабинет» — все `entity_type = "room"`. Именно
поэтому отдельный фильтр по действию не нужен.

Оговорка по регистру: в Postgres `ILIKE` корректно складывает регистр кириллицы,
в SQLite (на нём идут тесты) — только ASCII. Тесты пишем в один регистр, поведение
в продакшене от этого не зависит.

### Миграция

Одна: индекс `ix_audit_log_created_at` по `created_at` — по нему идёт сортировка
каждого запроса. Ревизия `20260807_0013`, `down_revision = "20260714_0012"`.

Колонку `actor_user_id` не добавляем: `actor_name` (это `User.display_name`) отвечает
на вопрос «кто», а для старых записей id всё равно негде взять.

## Обогащение payload

Часть payload'ов не содержит имени собственной сущности, и фразу из них не построить.
Дописываем ключи в существующие вызовы `_audit`:

| Место | Добавить |
|---|---|
| `groups/service.py:67` `set_homeroom_teacher` | `group_name` |
| `teachers/service.py:121` `mark_absent` | `teacher_name` |
| `teachers/service.py:139` `clear_absence` | `teacher_name` |
| `schedule_editor/service.py:292` `update` | вложенный `"lesson"`: `group_name`, `subject`, `date`, `time_slot` |
| `schedule_editor/service.py:318` `delete` | то же вложенное `"lesson"` |

У `lesson/update` payload приходит с `exclude_unset=True` и при пустом PATCH может быть
`{}` — вложенный слепок `"lesson"` гарантирует, что запись остаётся читаемой.

Записи, созданные до этого изменения, имён не получат: маппер откатывается на
`#{entity_id}`. Полиморфный join к семи таблицам сознательно не делаем — для удалённых
сущностей он всё равно ничего не вернёт, а read-путь перестанет быть одним сканом.

## Пробелы записи

**Импорт расписания.** `routers/imports.py:17` резолвит `actor` только ради проверки
прав и дальше его не использует. `import_schedule_from_payload` открывает собственную
сессию и коммитит независимо от сессии роутера, поэтому запись аудита делаем в роутере
после успешного импорта, отдельной транзакцией:
`entity_type="schedule_import"`, `action="import"`,
payload `{source_path, timetable_count, group_count, lesson_count, empty_day_count}`,
`entity_id` — id созданного `ScheduleImport` (`ImportResult` расширяем полем
`import_id`).

**Снятие классрука каскадом.** `clear_homeroom_teacher(session, teacher_id)`
(`groups/service.py:95`) вызывается единственный раз — из `delete_teacher`
(`teachers/service.py:78`) — и аудита не пишет. Сейчас факт виден лишь косвенно, как
`cleared_group_count` внутри чужого payload. Прокидываем `actor` и `teacher_name`
и пишем по записи на каждую затронутую группу:
`entity_type="group"`, `action="clear_homeroom_teacher"`,
payload `{group_name, teacher_name}`.

Ручное снятие через `set_homeroom_teacher(None)` уже логируется и не трогается.

## Каталог фраз

Разделы: `lesson` → Занятия, `group` → Группы, `teacher` → Преподаватели,
`room` → Кабинеты, `day_time_profile` → Профили дня,
`week_time_profile` → Профили недели, `user` → Пользователи,
`schedule_import` → Импорт.

Роли: `operator` → оператор, `admin` → администратор.

Даты в фразах — `DD.MM.YYYY` (конвенция проекта).

| entity/action | Фраза |
|---|---|
| `room/create` | Создан кабинет {name} |
| `room/delete` | Удалён кабинет {name}; при `unassigned_lesson_count > 0` — «, занятий без кабинета: {n}» |
| `room/exclude` | Кабинет {name} исключён из расписания; при `reason` — «: {reason}» |
| `room/restore` | Кабинет {name} возвращён в расписание |
| `group/rename` | Группа {old_name} переименована в {name} |
| `group/set_homeroom_teacher` | Классным руководителем группы {group_name} назначен {teacher_name}; при `teacher_name = null` — «У группы {group_name} снят классный руководитель» |
| `group/clear_homeroom_teacher` | У группы {group_name} снят классный руководитель {teacher_name} — удалён преподаватель |
| `group/delete` | Удалена группа {name}; при `deleted_lesson_count > 0` — «, удалено занятий: {n}» |
| `teacher/create` | Добавлен преподаватель {name} |
| `teacher/delete` | Удалён преподаватель {name}; далее ненулевые счётчики: занятий без преподавателя, снято отсутствий, групп без классрука |
| `teacher/mark_absent` | Отмечено отсутствие: {teacher_name}, {date}; «весь день» либо «пары {time_slot_start}–{time_slot_end}»; при `reason` — «, причина: {reason}» |
| `teacher/clear_absence` | Снято отсутствие: {teacher_name}, {date} |
| `day_time_profile/create\|update\|delete` | Создан / изменён / удалён профиль дня {name} |
| `week_time_profile/create\|update\|delete` | Создан / изменён / удалён профиль недели {name} |
| `user/create` | Создан пользователь {display_name} ({username}), роль: {role} |
| `user/revoke` | Отозван доступ пользователя {username} |
| `user/change_password` | Изменён пароль пользователя {username} |
| `lesson/create` | Добавлено занятие: {subject}, группа {group_name}, {date}, пара {time_slot} |
| `lesson/update` | Изменено занятие: {subject}, группа {group_name}, {date}, пара {time_slot} — далее перечень изменённых полей по-русски |
| `lesson/delete` | Удалено занятие: {subject}, группа {group_name}, {date}, пара {time_slot} |
| `schedule_import/import` | Импорт расписания: групп {group_count}, занятий {lesson_count} |

Идентичность занятия маппер берёт как `payload["lesson"]` с откатом на сам `payload`
(у `lesson/create` нужные ключи лежат на верхнем уровне).

Русские лейблы полей занятия для `lesson/update`: `group_name` → группа,
`course` → курс, `faculty` → отделение, `subject` → предмет,
`teacher_name`/`teacher_id` → преподаватель, `teacher_post` → должность,
`room_name` → кабинет, `date` → дата, `time_start` → начало, `time_end` → конец,
`weekday` → день недели, `week_number` → неделя, `time_slot` → пара,
`subgroup` → подгруппа, `lesson_type` → тип занятия.

Неизвестная пара entity/action не роняет страницу: фраза вырождается в
«{action} · {entity_type} #{entity_id}». Отсутствующее имя — в «#{entity_id}».

## Frontend

`apps/web/app/audit-page.tsx` — новый файл с `AuditPage({ accessToken })`. Это
client-компонент, импортируемый в ту же страницу; нового роута не появляется, SPA
остаётся SPA. Существующий код не переносим — `page.tsx` уже 3448 строк, добавлять
туда ещё 200 незачем.

В `page.tsx` три правки: импорт, белый список `isWorkspacePage` (`:123`) и цепочка
тернарников рендера секций (`:182`).

Компоновка по образцу `ProblemsPage` (`page.tsx:815`):

1. Шапка со счётчиком найденного
2. Тулбар: строка поиска (дебаунс 300 мс), период «с» / «по», кнопка «Обновить»
3. Чипы разделов — «Все» плюс восемь `entity_type`, стили `.problems-filter`
4. Список строк: время · пользователь с ролью · фраза
5. Кнопка «Показать ещё» — грузит следующие 100 и дописывает в конец
6. `users-empty` при пустом результате

Любая смена запроса, периода или чипа сбрасывает `offset` в 0 и перезагружает список.
Гонки ответов гасим счётчиком запросов: применяем только последний.

Классы `.audit-*` добавляются в `globals.css` рядом с `.problems-*` и переиспользуют
их визуальный язык. Дат в UI — `DD.MM.YYYY`, время — `HH:MM`.

## Тесты

Новый `apps/api/tests/test_audit_log.py`:

- доступ: оператор — 200, без токена — 401
- пагинация: `total` не зависит от `limit`; второй батч не пересекается с первым
- порядок: свежие записи первыми
- фильтры: по `entity_type`, по `date_from`/`date_to` (включая границу `date_to`)
- поиск: по имени пользователя, по значению из payload, по русскому слову действия
- фразы: по одному кейсу на каждую пару entity/action из каталога
- деградация: неизвестный `action` и запись без имени не роняют эндпоинт
- закрытые пробелы: импорт создаёт запись; удаление преподавателя с классным
  руководством создаёт запись на каждую группу

Регрессия: существующий `tests/test_schedule_editor.py:70` считает строки в
`audit_log` — новые записи не должны сломать этот счёт.

Проверки: pytest, `pnpm web:typecheck`, регенерация `openapi.yaml`.

## Что сознательно не делаем

- Не логируем входы в систему — это журнал безопасности, а не изменений
- Не показываем сырой JSON payload
- Не добавляем экспорт, удаление и ретенцию журнала
- Не добавляем `actor_user_id`
- Не переносим существующие страницы из `page.tsx` в отдельные файлы
