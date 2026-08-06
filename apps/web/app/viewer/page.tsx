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

const suggestionTypeOrder: Record<EntityType, number> = { group: 0, teacher: 1, room: 2 };

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
      .sort(
        (a, b) =>
          suggestionTypeOrder[a.entity.type] - suggestionTypeOrder[b.entity.type] ||
          a.at - b.at ||
          a.entity.name.localeCompare(b.entity.name, "ru-RU"),
      );
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
