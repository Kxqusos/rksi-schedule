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

type GroupWeekRow = {
  groupName: string;
  lessonsByDate: Record<string, PublicLesson[]>;
};

const weekdayLabels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

export default function ScheduleViewerPage() {
  const [week, setWeek] = useState<PublicScheduleWeek | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("Загрузка расписания.");
  const [busy, setBusy] = useState(true);

  const loadWeek = async () => {
    setBusy(true);
    try {
      const response = await fetch(`${apiBaseUrl}/schedule/public/latest-week`, {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as PublicScheduleWeek;
      setWeek(payload);
      setStatus(payload.days.length > 0 ? "Расписание загружено." : "Расписание пока не загружено.");
    } catch {
      setStatus("Не удалось загрузить расписание.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadWeek();
  }, []);

  const lessons = useMemo(() => week?.days.flatMap((day) => day.lessons) ?? [], [week]);
  const rows = useMemo(() => buildGroupRows(week?.days ?? []), [week]);
  const visibleRows = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("ru-RU");
    if (!normalizedQuery) {
      return rows;
    }
    return rows.filter((row) => row.groupName.toLocaleLowerCase("ru-RU").includes(normalizedQuery));
  }, [query, rows]);

  const weekRange = week?.week_start && week.week_end ? `${formatDate(week.week_start)} - ${formatDate(week.week_end)}` : "";

  return (
    <main className="viewer-shell">
      <header className="viewer-header">
        <div className="viewer-header__main">
          <div className="viewer-brand">RKSI Schedule</div>
          <h1>Расписание занятий</h1>
          <div className="viewer-week">
            {weekRange ? <span>{weekRange}</span> : <span>Неделя не выбрана</span>}
            {week?.week_number ? <strong>{week.week_number} неделя</strong> : null}
          </div>
        </div>
        <div className="viewer-header__side">
          <div className="viewer-stat">
            <span>Групп</span>
            <strong>{rows.length}</strong>
          </div>
          <div className="viewer-stat">
            <span>Занятий</span>
            <strong>{lessons.length}</strong>
          </div>
        </div>
      </header>

      <section className="viewer-toolbar" aria-label="Управление расписанием">
        <label className="viewer-search">
          <Search aria-hidden="true" size={17} strokeWidth={2} />
          <input
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Найти группу"
            value={query}
          />
        </label>
        <button className="viewer-refresh" disabled={busy} onClick={loadWeek} type="button">
          <RefreshCw aria-hidden="true" className={busy ? "viewer-refresh__icon viewer-refresh__icon--spin" : "viewer-refresh__icon"} size={16} />
          <span>{busy ? "Обновляем" : "Обновить"}</span>
        </button>
      </section>

      <section className="viewer-status" aria-live="polite">
        {status}
      </section>

      {busy ? (
        <ViewerSkeleton />
      ) : visibleRows.length > 0 && week ? (
        <section className="viewer-table-wrap" aria-label="Последняя актуальная неделя">
          <div className="viewer-table">
            <div className="viewer-table__head">
              <div className="viewer-table__group-head">Группа</div>
              {week.days.map((day, index) => (
                <div className="viewer-table__day-head" key={day.date}>
                  <strong>{weekdayLabels[index] ?? day.weekday}</strong>
                  <span>{formatShortDate(day.date)}</span>
                </div>
              ))}
            </div>

            {visibleRows.map((row) => (
              <div className="viewer-table__row" key={row.groupName}>
                <div className="viewer-table__group">{row.groupName}</div>
                {week.days.map((day) => (
                  <div className="viewer-table__cell" key={`${row.groupName}-${day.date}`}>
                    {(row.lessonsByDate[day.date] ?? []).length > 0 ? (
                      row.lessonsByDate[day.date].map((lesson) => <LessonCard key={lesson.id} lesson={lesson} />)
                    ) : (
                      <span className="viewer-empty-cell">Нет занятий</span>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </section>
      ) : (
        <section className="viewer-empty">
          {query.trim() ? "Группы по этому запросу не найдены." : "Расписание пока не загружено."}
        </section>
      )}
    </main>
  );
}

function LessonCard({ lesson }: { lesson: PublicLesson }) {
  return (
    <article className="viewer-lesson">
      <div className="viewer-lesson__top">
        <span>{lesson.time_slot} пара</span>
        <strong>{formatTimeRange(lesson.time_start, lesson.time_end)}</strong>
      </div>
      <div className="viewer-lesson__subject">{lesson.subject}</div>
      <div className="viewer-lesson__meta">
        {lesson.teacher_name ? <span>{lesson.teacher_name}</span> : null}
        {lesson.room_name ? <span>{lesson.room_name}</span> : null}
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

function buildGroupRows(days: PublicScheduleDay[]): GroupWeekRow[] {
  const rows = new Map<string, GroupWeekRow>();
  for (const day of days) {
    for (const lesson of day.lessons) {
      const row =
        rows.get(lesson.group_name) ??
        {
          groupName: lesson.group_name,
          lessonsByDate: {},
        };
      row.lessonsByDate[day.date] = [...(row.lessonsByDate[day.date] ?? []), lesson].sort(compareLessons);
      rows.set(lesson.group_name, row);
    }
  }
  return Array.from(rows.values()).sort((left, right) => left.groupName.localeCompare(right.groupName, "ru"));
}

function compareLessons(left: PublicLesson, right: PublicLesson) {
  return left.time_slot - right.time_slot || left.subgroup - right.subgroup || left.subject.localeCompare(right.subject, "ru");
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
