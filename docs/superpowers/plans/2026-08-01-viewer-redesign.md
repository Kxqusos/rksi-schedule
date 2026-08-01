# Viewer Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the public `/viewer` page into a clean, mobile-first, single-column schedule with day tabs, a light/dark theme toggle, and a redesigned lesson card — no horizontal scrolling anywhere.

**Architecture:** The page stays a single client component (`apps/web/app/viewer/page.tsx`) whose styles live in `apps/web/app/globals.css` under `.viewer-*` classes. All existing data-fetching logic (`/schedule/public/index`, `/schedule/public/by-*`, current-week rollover) is preserved. The table-with-day-columns layout is replaced by a vertical layout: a search box, a row of day tabs (Mon–Sat), and a vertical list of the selected day's lessons. Theme is applied via a `data-theme` attribute on the shell element, with CSS variables scoped to `.viewer-shell` for light and dark.

**Tech Stack:** Next.js 15 / React 19 / TypeScript, `lucide-react` icons, plain CSS in `globals.css`. No new dependencies.

## Global Constraints

- All user-facing copy in Russian; visible dates `DD.MM.YYYY`.
- No new npm dependencies; icons come from the already-installed `lucide-react`.
- No backend/API changes; the public endpoints already return everything needed.
- No changes to the admin SPA (`page.tsx`) or the current-week selection logic (`currentWeekNumber`, Sunday rollover) — reuse them unchanged.
- There is no frontend test harness in this repo; verification is `pnpm web:typecheck` plus visual checks against the running app at `http://127.0.0.1:3003/viewer` (Docker Compose must be up: `docker compose up`).
- Follow existing `.viewer-*` naming and the file's existing CSS style.

## File Structure

- Modify: `apps/web/app/viewer/page.tsx` — full component rewrite (markup + theme state + day tabs + auto-scroll + redesigned card). Same file, same responsibilities, new layout.
- Modify: `apps/web/app/globals.css` — replace the `.viewer-*` style block (lines ~36–492) with a new themed block; remove now-dead `.viewer-*` rules from the lower media queries.

---

### Task 1: Rewrite the viewer component

**Files:**
- Modify: `apps/web/app/viewer/page.tsx` (full replacement)

**Interfaces:**
- Consumes: existing public API shapes (`PublicIndex`, `PublicScheduleWeek`, `PublicScheduleDay`, `PublicLesson`) and the `apiBaseUrl` env; these type definitions are kept verbatim.
- Produces: CSS class contract consumed by Task 2 — `.viewer-shell` (with `data-theme` attr), `.viewer-inner`, `.viewer-topbar`, `.viewer-theme`, `.viewer-combobox`, `.viewer-search`, `.viewer-suggestions`, `.viewer-suggestion` (+ `--active`, `__icon`, `__name`, `__badge`), `.viewer-status`, `.viewer-empty`, `.viewer-skeleton` (+ `__card`), `.viewer-week-view`, `.viewer-tabs`, `.viewer-tab` (+ `--active`, `--today`, `__date`), `.viewer-day` (+ `__head`), `.viewer-day-empty`, `.viewer-lesson` (+ `__top`, `__pair`, `__time`, `__subject`, `__meta`).

- [ ] **Step 1: Replace the whole file with the new component**

Write `apps/web/app/viewer/page.tsx` with exactly this content:

```tsx
"use client";

import { DoorOpen, Moon, Search, Sun, User, Users } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8001";

type PublicLesson = {
  id: number;
  group_name: string;
  subject: string;
  teacher_name: string | null;
  room_name: string | null;
  date: string;
  time_start: string;
  time_end: string;
  weekday: number;
  week_number: number;
  time_slot: number;
  subgroup: number;
  lesson_type: string;
};

type PublicScheduleDay = {
  date: string;
  weekday: number;
  lessons: PublicLesson[];
};

type PublicScheduleWeek = {
  week_start: string | null;
  week_end: string | null;
  week_number: number | null;
  days: PublicScheduleDay[];
};

type EntityRef = { id: number; name: string };

type WeekRange = { week_number: number; start: string; end: string };

type PublicIndex = {
  groups: EntityRef[];
  teachers: EntityRef[];
  rooms: EntityRef[];
  weeks: number[];
  week_ranges: WeekRange[];
  latest_week: number | null;
};

type EntityType = "group" | "teacher" | "room";

type EntitySuggestion = { id: number; name: string; type: EntityType };

type Theme = "light" | "dark";

const weekdayLabels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const weekdayFull = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"];

const entityConfig: Record<EntityType, { label: string; listKey: "groups" | "teachers" | "rooms"; path: string; param: string }> = {
  group: { label: "Группа", listKey: "groups", path: "by-group", param: "group_id" },
  teacher: { label: "Преподаватель", listKey: "teachers", path: "by-teacher", param: "teacher_id" },
  room: { label: "Кабинет", listKey: "rooms", path: "by-room", param: "room_id" },
};

const SUGGESTION_LIMIT = 10;
const THEME_STORAGE_KEY = "viewer-theme";

function normalize(value: string) {
  return value.trim().toLocaleLowerCase("ru-RU");
}

function isForeignLanguage(subject: string) {
  return normalize(subject).includes("иностран");
}

function toLocalISODate(value: Date) {
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
}

// The schedule week rolls over at Sunday 00:00: from Sunday onward we show the
// upcoming Mon–Sat week. Maps that week's Monday to a seeded week_number, falling
// back to the most recent past week (covers breaks / out-of-year dates).
function currentWeekNumber(ranges: WeekRange[], latestWeek: number | null): number | null {
  if (ranges.length === 0) {
    return latestWeek;
  }
  const now = new Date();
  const dayOfWeek = now.getDay(); // 0 = Sunday
  const offsetToMonday = dayOfWeek === 0 ? 1 : 1 - dayOfWeek;
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() + offsetToMonday);
  const mondayISO = toLocalISODate(monday);

  const exact = ranges.find((range) => range.start === mondayISO);
  if (exact) {
    return exact.week_number;
  }
  const past = ranges.filter((range) => range.start <= mondayISO);
  if (past.length > 0) {
    return past[past.length - 1].week_number;
  }
  return ranges[0].week_number;
}

function msUntilNextSundayMidnight(now: Date) {
  const daysUntilSunday = (7 - now.getDay()) % 7;
  const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + (daysUntilSunday === 0 ? 7 : daysUntilSunday));
  const delay = next.getTime() - now.getTime();
  return delay > 0 ? delay : delay + 7 * 24 * 60 * 60 * 1000;
}

export default function ScheduleViewerPage() {
  const [index, setIndex] = useState<PublicIndex | null>(null);
  const [week, setWeek] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [selected, setSelected] = useState<EntitySuggestion | null>(null);
  const [weekData, setWeekData] = useState<PublicScheduleWeek | null>(null);
  const [status, setStatus] = useState("Загрузка расписания.");
  const [busy, setBusy] = useState(true);
  const [activeDate, setActiveDate] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>("light");
  const comboboxRef = useRef<HTMLDivElement>(null);
  const weekViewRef = useRef<HTMLDivElement>(null);

  const todayISO = toLocalISODate(new Date());

  // Resolve theme from storage, then system preference, after mount (avoids SSR mismatch).
  useEffect(() => {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark") {
      setTheme(stored);
      return;
    }
    if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
      setTheme("dark");
    }
  }, []);

  const toggleTheme = () => {
    setTheme((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
      return next;
    });
  };

  const loadIndex = async () => {
    setBusy(true);
    try {
      const response = await fetch(`${apiBaseUrl}/schedule/public/index`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as PublicIndex;
      setIndex(payload);
      setWeek(currentWeekNumber(payload.week_ranges, payload.latest_week));
      setStatus(payload.groups.length + payload.teachers.length + payload.rooms.length > 0 ? "" : "Расписание пока не загружено.");
    } catch {
      setStatus("Не удалось загрузить расписание.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadIndex();
  }, []);

  // Roll the displayed week over at Sunday 00:00 without a reload.
  useEffect(() => {
    if (!index) {
      return;
    }
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      timer = setTimeout(() => {
        setWeek(currentWeekNumber(index.week_ranges, index.latest_week));
        schedule();
      }, msUntilNextSundayMidnight(new Date()));
    };
    schedule();
    return () => clearTimeout(timer);
  }, [index]);

  const allEntities = useMemo<EntitySuggestion[]>(() => {
    if (!index) {
      return [];
    }
    return [
      ...index.groups.map((entity) => ({ ...entity, type: "group" as const })),
      ...index.teachers.map((entity) => ({ ...entity, type: "teacher" as const })),
      ...index.rooms.map((entity) => ({ ...entity, type: "room" as const })),
    ];
  }, [index]);

  const suggestions = useMemo<EntitySuggestion[]>(() => {
    const normalized = normalize(query);
    if (!normalized) {
      return [];
    }
    const scored = allEntities
      .map((entity) => ({ entity, at: normalize(entity.name).indexOf(normalized) }))
      .filter((candidate) => candidate.at >= 0)
      .sort((a, b) => a.at - b.at || a.entity.name.localeCompare(b.entity.name, "ru-RU"));
    return scored.slice(0, SUGGESTION_LIMIT).map((candidate) => candidate.entity);
  }, [allEntities, query]);

  // Suggestions never query the schedule; only picking one does.
  const showSuggestions = open && suggestions.length > 0;

  useEffect(() => {
    if (!showSuggestions) {
      return;
    }
    const handlePointerDown = (event: PointerEvent) => {
      if (comboboxRef.current && !comboboxRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [showSuggestions]);

  const loadWeek = async () => {
    if (selected == null || week == null) {
      setWeekData(null);
      return;
    }
    setBusy(true);
    try {
      const config = entityConfig[selected.type];
      const response = await fetch(
        `${apiBaseUrl}/schedule/public/${config.path}?${config.param}=${selected.id}&week=${week}`,
        { cache: "no-store" },
      );
      if (!response.ok) {
        throw new Error(await response.text());
      }
      setWeekData((await response.json()) as PublicScheduleWeek);
      setStatus("");
    } catch {
      setStatus("Не удалось загрузить расписание.");
    } finally {
      setBusy(false);
    }
  };

  // Auto-loads whenever the selection or displayed week changes (no manual refresh button).
  useEffect(() => {
    void loadWeek();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, week]);

  const days = useMemo(() => weekData?.days.filter((day) => day.weekday !== 7) ?? [], [weekData]);

  // Keep the active tab valid: prefer today, else the first day.
  useEffect(() => {
    if (days.length === 0) {
      setActiveDate(null);
      return;
    }
    setActiveDate((prev) => {
      if (prev && days.some((day) => day.date === prev)) {
        return prev;
      }
      const today = days.find((day) => day.date === todayISO);
      return today ? today.date : days[0].date;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days]);

  // On mobile, bring the day view into focus when a new schedule loads.
  useEffect(() => {
    if (!weekData || days.length === 0) {
      return;
    }
    if (window.innerWidth <= 767) {
      weekViewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weekData]);

  const pickSuggestion = (suggestion: EntitySuggestion) => {
    setSelected(suggestion);
    setQuery(suggestion.name);
    setOpen(false);
    setHighlight(0);
  };

  const onQueryChange = (value: string) => {
    setQuery(value);
    setOpen(true);
    setHighlight(0);
  };

  const onSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showSuggestions) {
      if (event.key === "ArrowDown" && suggestions.length > 0) {
        setOpen(true);
        setHighlight(0);
        event.preventDefault();
      }
      return;
    }
    if (event.key === "ArrowDown") {
      setHighlight((current) => (current + 1) % suggestions.length);
      event.preventDefault();
    } else if (event.key === "ArrowUp") {
      setHighlight((current) => (current - 1 + suggestions.length) % suggestions.length);
      event.preventDefault();
    } else if (event.key === "Enter") {
      const choice = suggestions[highlight];
      if (choice) {
        pickSuggestion(choice);
        event.preventDefault();
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  const activeIndex = days.findIndex((day) => day.date === activeDate);
  const activeDay = activeIndex >= 0 ? days[activeIndex] : null;

  return (
    <main className="viewer-shell" data-theme={theme}>
      <div className="viewer-inner">
        <div className="viewer-topbar">
          <button
            className="viewer-theme"
            onClick={toggleTheme}
            type="button"
            aria-label={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
          >
            {theme === "dark" ? <Sun aria-hidden="true" size={18} /> : <Moon aria-hidden="true" size={18} />}
          </button>
        </div>

        <div className="viewer-combobox" ref={comboboxRef}>
          <label className="viewer-search">
            <Search aria-hidden="true" size={18} strokeWidth={2} />
            <input
              aria-activedescendant={showSuggestions ? `viewer-suggestion-${highlight}` : undefined}
              aria-autocomplete="list"
              aria-controls="viewer-suggestions"
              aria-expanded={showSuggestions}
              autoComplete="off"
              onChange={(event) => onQueryChange(event.target.value)}
              onFocus={() => setOpen(true)}
              onKeyDown={onSearchKeyDown}
              placeholder="Найти группу, преподавателя или кабинет"
              role="combobox"
              value={query}
            />
          </label>
          {showSuggestions ? (
            <ul className="viewer-suggestions" id="viewer-suggestions" role="listbox">
              {suggestions.map((suggestion, itemIndex) => (
                <li
                  aria-selected={itemIndex === highlight}
                  className={itemIndex === highlight ? "viewer-suggestion viewer-suggestion--active" : "viewer-suggestion"}
                  id={`viewer-suggestion-${itemIndex}`}
                  key={`${suggestion.type}-${suggestion.id}`}
                  onMouseEnter={() => setHighlight(itemIndex)}
                  onPointerDown={(event) => {
                    event.preventDefault();
                    pickSuggestion(suggestion);
                  }}
                  role="option"
                >
                  <SuggestionIcon type={suggestion.type} />
                  <span className="viewer-suggestion__name">{suggestion.name}</span>
                  <span className="viewer-suggestion__badge">{entityConfig[suggestion.type].label}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        {status ? (
          <div className="viewer-status" aria-live="polite">
            {status}
          </div>
        ) : null}

        {selected == null ? (
          <div className="viewer-empty">Начните вводить группу, преподавателя или кабинет.</div>
        ) : busy ? (
          <ViewerSkeleton />
        ) : activeDay ? (
          <div className="viewer-week-view" ref={weekViewRef}>
            <div className="viewer-tabs" role="tablist">
              {days.map((day, dayIndex) => {
                const isActive = day.date === activeDate;
                const isToday = day.date === todayISO;
                const className = ["viewer-tab", isActive ? "viewer-tab--active" : "", isToday ? "viewer-tab--today" : ""]
                  .filter(Boolean)
                  .join(" ");
                return (
                  <button
                    aria-selected={isActive}
                    className={className}
                    key={day.date}
                    onClick={() => setActiveDate(day.date)}
                    role="tab"
                    type="button"
                  >
                    <strong>{weekdayLabels[dayIndex] ?? day.weekday}</strong>
                    <span className="viewer-tab__date">{formatShortDate(day.date)}</span>
                  </button>
                );
              })}
            </div>

            <section className="viewer-day" aria-label={`Расписание: ${selected.name}`}>
              <div className="viewer-day__head">
                {weekdayFull[activeIndex] ?? ""} · {formatShortDate(activeDay.date)}
              </div>
              {activeDay.lessons.length > 0 ? (
                activeDay.lessons.map((lesson) => (
                  <LessonCard entityType={selected.type} key={lesson.id} lesson={lesson} />
                ))
              ) : (
                <div className="viewer-day-empty">В этот день занятий нет.</div>
              )}
            </section>
          </div>
        ) : (
          <div className="viewer-empty">Расписание пока не загружено.</div>
        )}
      </div>
    </main>
  );
}

function SuggestionIcon({ type }: { type: EntityType }) {
  const Icon = type === "group" ? Users : type === "teacher" ? User : DoorOpen;
  return <Icon aria-hidden="true" className="viewer-suggestion__icon" size={16} strokeWidth={2} />;
}

function LessonCard({ lesson, entityType }: { lesson: PublicLesson; entityType: EntityType }) {
  const metaParts: string[] = [];
  if (entityType !== "group") {
    metaParts.push(lesson.group_name);
  }
  if (entityType !== "teacher" && lesson.teacher_name) {
    metaParts.push(lesson.teacher_name);
  }
  if (entityType !== "room" && lesson.room_name) {
    metaParts.push(lesson.room_name);
  }
  if (lesson.subgroup > 0 && !isForeignLanguage(lesson.subject)) {
    metaParts.push(`${lesson.subgroup} подгр.`);
  }
  return (
    <article className="viewer-lesson">
      <div className="viewer-lesson__top">
        <span className="viewer-lesson__pair">{lesson.time_slot} пара</span>
        <span className="viewer-lesson__time">{formatTimeRange(lesson.time_start, lesson.time_end)}</span>
      </div>
      <div className="viewer-lesson__subject">{lesson.subject}</div>
      {metaParts.length > 0 ? (
        <div className="viewer-lesson__meta">
          {metaParts.map((part, partIndex) => (
            <span key={partIndex}>{part}</span>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function ViewerSkeleton() {
  return (
    <div className="viewer-skeleton" aria-label="Загрузка">
      {Array.from({ length: 5 }, (_, index) => (
        <div className="viewer-skeleton__card" key={index} />
      ))}
    </div>
  );
}

function formatShortDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) {
    return value;
  }
  return `${String(day).padStart(2, "0")}.${String(month).padStart(2, "0")}.${year}`;
}

function formatTimeRange(start: string, end: string) {
  return `${start.slice(0, 5)}-${end.slice(0, 5)}`;
}
```

- [ ] **Step 2: Typecheck**

Run: `pnpm web:typecheck`
Expected: exits 0, no errors. (The old `formatDate`/`formatPlainDate`/`RefreshCw`/`lessons`/`weekRange` are gone; nothing should reference them.)

- [ ] **Step 3: Commit**

```bash
git add apps/web/app/viewer/page.tsx
git commit -m "feat(viewer): mobile-first layout, day tabs, theme toggle, redesigned card"
```

---

### Task 2: Replace the viewer CSS block with the themed design

**Files:**
- Modify: `apps/web/app/globals.css` (replace lines ~36–492, i.e. from `.viewer-shell {` through the closing `}` of the `@media (min-width: 2400px)` block that ends just before `.auth-shell {`)

**Interfaces:**
- Consumes: the class contract produced by Task 1.
- Produces: themed `.viewer-*` styles; light is the default, `.viewer-shell[data-theme="dark"]` overrides the variables.

- [ ] **Step 1: Replace the old viewer style block**

Open `apps/web/app/globals.css`. Delete everything from the line `.viewer-shell {` (first occurrence, ~line 36) up to and including the closing `}` of the `@media (min-width: 2400px)` block (the `}` immediately before `.auth-shell {`, ~line 492). Replace it with:

```css
.viewer-shell {
  --v-bg: #f5f7fb;
  --v-surface: #ffffff;
  --v-surface-2: #f3f4f6;
  --v-border: rgba(17, 24, 39, 0.12);
  --v-text: #111827;
  --v-muted: #6b7280;
  --v-accent: #4f7fd8;
  --v-accent-soft: #eef4ff;
  --v-today: #16a34a;
  min-height: 100vh;
  background: var(--v-bg);
  color: var(--v-text);
  padding: 24px 16px;
}

.viewer-shell[data-theme="dark"] {
  --v-bg: #0f1217;
  --v-surface: #151a21;
  --v-surface-2: #1b222c;
  --v-border: rgba(255, 255, 255, 0.1);
  --v-text: #eef2f6;
  --v-muted: rgba(238, 242, 246, 0.6);
  --v-accent: #6f9bec;
  --v-accent-soft: rgba(79, 127, 216, 0.16);
  --v-today: #34d399;
}

.viewer-inner {
  width: min(720px, 100%);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.viewer-topbar {
  display: flex;
  justify-content: flex-end;
}

.viewer-theme {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--v-border);
  border-radius: 10px;
  background: var(--v-surface);
  color: var(--v-text);
  cursor: pointer;
}

.viewer-combobox {
  position: relative;
  width: 100%;
}

.viewer-search {
  width: 100%;
  min-height: 46px;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--v-border);
  border-radius: 12px;
  background: var(--v-surface);
  color: var(--v-muted);
  padding: 0 14px;
}

.viewer-search input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--v-text);
  font-size: 15px;
}

.viewer-suggestions {
  position: absolute;
  z-index: 20;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  margin: 0;
  padding: 4px;
  list-style: none;
  max-height: 340px;
  overflow-y: auto;
  border: 1px solid var(--v-border);
  border-radius: 12px;
  background: var(--v-surface);
  box-shadow: 0 12px 28px rgba(17, 24, 39, 0.18);
}

.viewer-suggestion {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--v-text);
}

.viewer-suggestion--active {
  background: var(--v-surface-2);
}

.viewer-suggestion__icon {
  flex-shrink: 0;
  color: var(--v-muted);
}

.viewer-suggestion__name {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  font-weight: 620;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.viewer-suggestion__badge {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 640;
  color: var(--v-muted);
}

.viewer-status {
  color: var(--v-muted);
  font-size: 14px;
  line-height: 1.4;
}

.viewer-empty {
  border: 1px dashed var(--v-border);
  border-radius: 12px;
  background: var(--v-surface);
  color: var(--v-muted);
  padding: 28px 20px;
  text-align: center;
  font-size: 15px;
}

.viewer-week-view {
  display: flex;
  flex-direction: column;
  gap: 14px;
  scroll-margin-top: 12px;
}

.viewer-tabs {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 6px;
}

.viewer-tab {
  display: grid;
  gap: 2px;
  justify-items: center;
  align-content: center;
  min-height: 52px;
  min-width: 0;
  padding: 6px 2px;
  border: 1px solid var(--v-border);
  border-radius: 12px;
  background: var(--v-surface);
  color: var(--v-muted);
  cursor: pointer;
}

.viewer-tab strong {
  font-size: 14px;
  font-weight: 760;
  line-height: 1;
  color: var(--v-text);
}

.viewer-tab__date {
  font-size: 11px;
  line-height: 1;
  color: var(--v-muted);
}

.viewer-tab--today {
  position: relative;
}

.viewer-tab--today strong {
  color: var(--v-today);
}

.viewer-tab--today::after {
  content: "";
  position: absolute;
  top: 6px;
  right: 6px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--v-today);
}

.viewer-tab--active {
  border-color: var(--v-accent);
  background: var(--v-accent-soft);
}

.viewer-tab--active strong {
  color: var(--v-accent);
}

.viewer-day {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.viewer-day__head {
  color: var(--v-muted);
  font-size: 13px;
  font-weight: 740;
}

.viewer-day-empty {
  border: 1px dashed var(--v-border);
  border-radius: 12px;
  background: var(--v-surface);
  color: var(--v-muted);
  padding: 20px;
  text-align: center;
  font-size: 14px;
}

.viewer-lesson {
  display: flex;
  flex-direction: column;
  gap: 6px;
  border: 1px solid var(--v-border);
  border-left: 3px solid var(--v-accent);
  border-radius: 12px;
  background: var(--v-surface);
  padding: 12px 14px;
}

.viewer-lesson__top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.viewer-lesson__pair {
  font-size: 12px;
  font-weight: 740;
  color: var(--v-muted);
}

.viewer-lesson__time {
  font-size: 13px;
  font-weight: 780;
  color: var(--v-text);
  font-variant-numeric: tabular-nums;
}

.viewer-lesson__subject {
  font-size: 16px;
  font-weight: 720;
  line-height: 1.3;
  color: var(--v-text);
  overflow-wrap: anywhere;
}

.viewer-lesson__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  color: var(--v-muted);
  font-size: 13px;
}

.viewer-lesson__meta span {
  display: inline-flex;
  align-items: center;
  overflow-wrap: anywhere;
}

.viewer-lesson__meta span:not(:first-child)::before {
  content: "·";
  margin-right: 8px;
  color: var(--v-muted);
}

.viewer-skeleton {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.viewer-skeleton__card {
  height: 82px;
  border-radius: 12px;
  background: linear-gradient(90deg, var(--v-surface-2) 0%, var(--v-surface) 48%, var(--v-surface-2) 100%);
  background-size: 220% 100%;
  animation: viewer-loading 1.2s ease-in-out infinite;
}

@keyframes viewer-loading {
  0% {
    background-position: 120% 0;
  }
  100% {
    background-position: -120% 0;
  }
}

@media (max-width: 767px) {
  .viewer-shell {
    padding: 16px 12px;
  }

  .viewer-tab strong {
    font-size: 13px;
  }
}

@media (max-width: 360px) {
  .viewer-tab__date {
    display: none;
  }
}
```

- [ ] **Step 2: Verify the file still parses (no stray braces)**

Run: `pnpm web:typecheck`
Expected: exits 0. (Typecheck won't lint CSS, but confirms nothing in the TS build broke.) Also visually confirm in the editor that the block immediately before `.auth-shell {` is the new `@media (max-width: 360px)` block's closing `}`.

- [ ] **Step 3: Commit**

```bash
git add apps/web/app/globals.css
git commit -m "feat(viewer): themed light/dark styles for redesigned layout"
```

---

### Task 3: Remove dead viewer rules from the lower media queries and verify end-to-end

**Files:**
- Modify: `apps/web/app/globals.css` (the `@media (max-width: 1366px)`, `1200px`, `1024px`, `880px`, and `767px` blocks — remove only rules targeting classes that no longer exist)

**Interfaces:**
- Consumes: nothing new.
- Produces: a globals.css with no `.viewer-table*`, `.viewer-header*`, `.viewer-stat`, `.viewer-week`, `.viewer-toolbar`, `.viewer-refresh`, `.viewer-skeleton__row`, or `.viewer-segmented*` references.

Removed classes to purge from the five lower media queries: `.viewer-table`, `.viewer-table__head`, `.viewer-table__row`, `.viewer-table-wrap`, `.viewer-header`, `.viewer-header h1`, `.viewer-header__side`, `.viewer-stat`, `.viewer-week`, `.viewer-toolbar`, `.viewer-refresh`, `.viewer-combobox`, `.viewer-search` (the width override is redundant now), `.viewer-skeleton__row`. Keep every non-viewer rule (`.sidebar`, `.users-grid`, `.import-*`, `.schedule-*`, etc.) and keep the `.viewer-shell` padding overrides.

- [ ] **Step 1: Purge the `@media (max-width: 1366px)` viewer table rules**

Find and delete these two rule blocks inside the `@media (max-width: 1366px)` block (keep `.viewer-shell { padding: 20px; }` — it is still valid):

```css
  .viewer-table {
    min-width: 1080px;
  }

  .viewer-table__head,
  .viewer-table__row {
    grid-template-columns: 132px repeat(7, minmax(126px, 1fr));
  }

```

- [ ] **Step 2: Purge the `@media (max-width: 1200px)` viewer rules**

Delete these two blocks inside `@media (max-width: 1200px)` (keep `.sidebar`, `.import-meta`, `.schedule-toolbar`, `.users-grid`, `.rooms-grid`, `.teachers-grid`):

```css
  .viewer-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .viewer-table {
    min-width: 1040px;
  }

```

- [ ] **Step 3: Purge the `@media (max-width: 1024px)` viewer rules**

Delete these blocks inside `@media (max-width: 1024px)` (keep `.app-shell`, `.sidebar*`, `.import-*`, `.schedule-toolbar`, grids):

```css
  .viewer-header h1 {
    font-size: 28px;
  }

  .viewer-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .viewer-combobox,
  .viewer-search {
    width: 100%;
  }

  .viewer-refresh {
    align-self: flex-start;
  }

```

- [ ] **Step 4: Purge the `@media (max-width: 880px)` viewer rules**

Delete these two blocks inside `@media (max-width: 880px)` (keep `.viewer-shell { gap: 14px; padding: 16px; }`, `.app-shell`, `.sidebar__mark`, `.import-meta`, `.schedule-*`):

```css
  .viewer-header__side {
    width: 100%;
  }

  .viewer-stat {
    flex: 1 1 0;
  }

```

- [ ] **Step 5: Purge the `@media (max-width: 767px)` viewer rules**

Inside `@media (max-width: 767px)`, keep `.viewer-shell { padding: 12px; }`, then delete these blocks (keep `.app-shell`, `.sidebar*`):

```css
  .viewer-header {
    gap: 14px;
    padding-bottom: 14px;
  }

  .viewer-header h1 {
    font-size: 24px;
  }

  .viewer-week {
    font-size: 13px;
  }

  .viewer-header__side {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }

  .viewer-table-wrap {
    margin-inline: -12px;
    border-left: 0;
    border-right: 0;
    border-radius: 0;
  }

  .viewer-table {
    min-width: 960px;
  }

  .viewer-table__head,
  .viewer-table__row {
    grid-template-columns: 118px repeat(7, minmax(120px, 1fr));
  }

  .viewer-skeleton__row {
    grid-template-columns: 96px 1fr 1fr;
  }

```

- [ ] **Step 6: Confirm no dead viewer references remain**

Run: `rg -n "viewer-table|viewer-header|viewer-stat|viewer-week|viewer-toolbar|viewer-refresh|viewer-segmented|viewer-skeleton__row" apps/web/app/globals.css`
Expected: no matches (empty output).

- [ ] **Step 7: Typecheck**

Run: `pnpm web:typecheck`
Expected: exits 0.

- [ ] **Step 8: Visual verification against the running app**

Ensure the stack is up (`docker compose up`). Then, using Playwright (or a manual browser), open `http://127.0.0.1:3003/viewer` and check:

1. **Desktop (1280×800):** single centered column ≤720px; only a theme toggle in the top-right; search box; after picking a group, day tabs (Пн–Сб) appear with today's tab highlighted (green dot + green label) and selected (accent fill); the day heading and a vertical list of lesson cards render; no horizontal page scroll.
2. **Mobile (390×844):** all six tabs fit on one row without horizontal scroll; lesson card meta (teacher · room) wraps instead of overflowing; on selecting an entity the view scrolls to the day tabs.
3. **Theme toggle:** clicking it flips light⇄dark; reload preserves the choice (localStorage). With no stored choice, it follows the OS preference.
4. **Foreign language:** a foreign-language lesson (subject contains «иностран») shows no «N подгр.» chip; a non-foreign subgroup lesson still shows it.

Capture a screenshot in each theme at mobile and desktop widths to confirm.

- [ ] **Step 9: Commit**

```bash
git add apps/web/app/globals.css
git commit -m "refactor(viewer): drop dead responsive rules from old table layout"
```

---

## Self-Review

**Spec coverage:**
- Mobile-first single column, no horizontal scroll → Task 1 layout + Task 2 `.viewer-inner`/`.viewer-tabs` grid + Task 3 cleanup. ✓
- Minimal header (theme toggle only; no brand/H1/week/name/count) → Task 1 `.viewer-topbar`. ✓
- Search with suggestions, auto-load on pick, no refresh button → Task 1 (button removed, effect retained). ✓
- Day tabs Пн–Сб, one day, default current day → Task 1 `days`/`activeDate` effect. ✓
- Highlight current day → Task 1 `viewer-tab--today` + Task 2 dot/label styles. ✓
- Mobile auto-scroll to current day → Task 1 `weekViewRef` effect. ✓
- Redesigned lesson card, wrapping meta → Task 1 `LessonCard` + Task 2 `.viewer-lesson*`. ✓
- Remove foreign-language subgroup label → Task 1 `isForeignLanguage` guard. ✓
- Light/dark theme, system default, toggle, localStorage → Task 1 theme state + Task 2 variables. ✓
- Russian copy, Inter font (already global) → Task 1 copy; font unchanged. ✓

**Placeholder scan:** No TBD/TODO; all code and edits are concrete. ✓

**Type consistency:** Class names used in Task 1 markup match the selectors defined in Task 2 (`viewer-week-view`, `viewer-tab`/`--active`/`--today`/`__date`, `viewer-day`/`__head`, `viewer-day-empty`, `viewer-lesson__pair`/`__time`, `viewer-skeleton__card`, `viewer-theme`, `viewer-inner`, `viewer-topbar`). `todayISO`, `activeDate`, `activeIndex`, `days` are all defined before use. ✓
