"use client";

import { RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

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

type PublicIndex = {
  groups: EntityRef[];
  teachers: EntityRef[];
  rooms: EntityRef[];
  weeks: number[];
  latest_week: number | null;
};

type EntityType = "group" | "teacher" | "room";

const weekdayLabels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

const entityConfig: Record<EntityType, { label: string; listKey: "groups" | "teachers" | "rooms"; path: string; param: string }> = {
  group: { label: "Группа", listKey: "groups", path: "by-group", param: "group_id" },
  teacher: { label: "Преподаватель", listKey: "teachers", path: "by-teacher", param: "teacher_id" },
  room: { label: "Кабинет", listKey: "rooms", path: "by-room", param: "room_id" },
};

export default function ScheduleViewerPage() {
  const [index, setIndex] = useState<PublicIndex | null>(null);
  const [entityType, setEntityType] = useState<EntityType>("group");
  const [entityId, setEntityId] = useState<number | null>(null);
  const [week, setWeek] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [weekData, setWeekData] = useState<PublicScheduleWeek | null>(null);
  const [status, setStatus] = useState("Загрузка расписания.");
  const [busy, setBusy] = useState(true);

  const loadIndex = async () => {
    setBusy(true);
    try {
      const response = await fetch(`${apiBaseUrl}/schedule/public/index`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as PublicIndex;
      setIndex(payload);
      setWeek(payload.latest_week ?? payload.weeks[payload.weeks.length - 1] ?? null);
      setEntityId(payload.groups[0]?.id ?? null);
      setStatus(payload.groups.length > 0 ? "" : "Расписание пока не загружено.");
    } catch {
      setStatus("Не удалось загрузить расписание.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadIndex();
  }, []);

  const entities = useMemo<EntityRef[]>(() => (index ? index[entityConfig[entityType].listKey] : []), [index, entityType]);

  const visibleEntities = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("ru-RU");
    if (!normalized) {
      return entities;
    }
    return entities.filter((entity) => entity.name.toLocaleLowerCase("ru-RU").includes(normalized));
  }, [entities, query]);

  const loadWeek = async () => {
    if (entityId == null || week == null) {
      setWeekData(null);
      return;
    }
    setBusy(true);
    try {
      const config = entityConfig[entityType];
      const response = await fetch(
        `${apiBaseUrl}/schedule/public/${config.path}?${config.param}=${entityId}&week=${week}`,
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

  useEffect(() => {
    void loadWeek();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityType, entityId, week]);

  const selectEntityType = (nextType: EntityType) => {
    setEntityType(nextType);
    setQuery("");
    setEntityId(index?.[entityConfig[nextType].listKey][0]?.id ?? null);
  };

  const selectedEntity = entities.find((entity) => entity.id === entityId) ?? null;
  const lessons = useMemo(() => weekData?.days.flatMap((day) => day.lessons) ?? [], [weekData]);
  const weekRange =
    weekData?.week_start && weekData.week_end ? `${formatDate(weekData.week_start)} - ${formatDate(weekData.week_end)}` : "";

  return (
    <main className="viewer-shell">
      <header className="viewer-header">
        <div className="viewer-header__main">
          <div className="viewer-brand">RKSI Schedule</div>
          <h1>Расписание занятий</h1>
          <div className="viewer-week">
            {weekRange ? <span>{weekRange}</span> : <span>Неделя не выбрана</span>}
            {weekData?.week_number ? <strong>{weekData.week_number} неделя</strong> : null}
          </div>
        </div>
        <div className="viewer-header__side">
          <div className="viewer-stat">
            <span>{entityConfig[entityType].label}</span>
            <strong>{selectedEntity?.name ?? "—"}</strong>
          </div>
          <div className="viewer-stat">
            <span>Занятий</span>
            <strong>{lessons.length}</strong>
          </div>
        </div>
      </header>

      <section className="viewer-toolbar" aria-label="Управление расписанием">
        <div className="viewer-segmented" role="tablist" aria-label="Тип поиска">
          {(Object.keys(entityConfig) as EntityType[]).map((type) => (
            <button
              aria-selected={entityType === type}
              className={entityType === type ? "viewer-segmented__button viewer-segmented__button--active" : "viewer-segmented__button"}
              key={type}
              onClick={() => selectEntityType(type)}
              role="tab"
              type="button"
            >
              {entityConfig[type].label}
            </button>
          ))}
        </div>
        <label className="viewer-search">
          <Search aria-hidden="true" size={17} strokeWidth={2} />
          <input
            onChange={(event) => setQuery(event.target.value)}
            placeholder={`Найти: ${entityConfig[entityType].label.toLocaleLowerCase("ru-RU")}`}
            value={query}
          />
        </label>
        <select
          aria-label={entityConfig[entityType].label}
          className="viewer-select"
          onChange={(event) => setEntityId(Number(event.target.value))}
          value={entityId ?? ""}
        >
          {visibleEntities.map((entity) => (
            <option key={entity.id} value={entity.id}>
              {entity.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Неделя"
          className="viewer-select"
          onChange={(event) => setWeek(Number(event.target.value))}
          value={week ?? ""}
        >
          {(index?.weeks ?? []).map((weekNumber) => (
            <option key={weekNumber} value={weekNumber}>
              {weekNumber} неделя
            </option>
          ))}
        </select>
        <button className="viewer-refresh" disabled={busy} onClick={loadWeek} type="button">
          <RefreshCw aria-hidden="true" className={busy ? "viewer-refresh__icon viewer-refresh__icon--spin" : "viewer-refresh__icon"} size={16} />
          <span>{busy ? "Обновляем" : "Обновить"}</span>
        </button>
      </section>

      {status ? (
        <section className="viewer-status" aria-live="polite">
          {status}
        </section>
      ) : null}

      {busy ? (
        <ViewerSkeleton />
      ) : weekData && selectedEntity ? (
        <section className="viewer-table-wrap" aria-label={`Расписание: ${selectedEntity.name}`}>
          <div className="viewer-table">
            <div className="viewer-table__head">
              <div className="viewer-table__group-head">{entityConfig[entityType].label}</div>
              {weekData.days.map((day, dayIndex) => (
                <div className="viewer-table__day-head" key={day.date}>
                  <strong>{weekdayLabels[dayIndex] ?? day.weekday}</strong>
                  <span>{formatShortDate(day.date)}</span>
                </div>
              ))}
            </div>
            <div className="viewer-table__row">
              <div className="viewer-table__group">{selectedEntity.name}</div>
              {weekData.days.map((day) => (
                <div className="viewer-table__cell" key={`${selectedEntity.id}-${day.date}`}>
                  {day.lessons.length > 0 ? (
                    day.lessons.map((lesson) => <LessonCard entityType={entityType} key={lesson.id} lesson={lesson} />)
                  ) : (
                    <span className="viewer-empty-cell">Нет занятий</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>
      ) : (
        <section className="viewer-empty">Расписание пока не загружено.</section>
      )}
    </main>
  );
}

function LessonCard({ lesson, entityType }: { lesson: PublicLesson; entityType: EntityType }) {
  return (
    <article className="viewer-lesson">
      <div className="viewer-lesson__top">
        <span>{lesson.time_slot} пара</span>
        <strong>{formatTimeRange(lesson.time_start, lesson.time_end)}</strong>
      </div>
      <div className="viewer-lesson__subject">{lesson.subject}</div>
      <div className="viewer-lesson__meta">
        {entityType !== "group" ? <span>{lesson.group_name}</span> : null}
        {entityType !== "teacher" && lesson.teacher_name ? <span>{lesson.teacher_name}</span> : null}
        {entityType !== "room" && lesson.room_name ? <span>{lesson.room_name}</span> : null}
        {lesson.subgroup > 0 ? <span>{lesson.subgroup} подгр.</span> : null}
      </div>
    </article>
  );
}

function ViewerSkeleton() {
  return (
    <section className="viewer-skeleton" aria-label="Загрузка">
      {Array.from({ length: 8 }, (_, index) => (
        <div className="viewer-skeleton__row" key={index}>
          <div />
          <span />
          <span />
          <span />
        </div>
      ))}
    </section>
  );
}

function formatDate(value: string) {
  return formatPlainDate(value);
}

function formatShortDate(value: string) {
  return formatPlainDate(value);
}

function formatPlainDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) {
    return value;
  }
  return `${String(day).padStart(2, "0")}.${String(month).padStart(2, "0")}.${year}`;
}

function formatTimeRange(start: string, end: string) {
  return `${start.slice(0, 5)}-${end.slice(0, 5)}`;
}
