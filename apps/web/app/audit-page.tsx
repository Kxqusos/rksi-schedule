"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8001";
const pageSize = 100;
const searchDebounceMs = 300;

const entityFilters = [
  { value: "all", label: "Все" },
  { value: "lesson", label: "Занятия" },
  { value: "group", label: "Группы" },
  { value: "teacher", label: "Преподаватели" },
  { value: "room", label: "Кабинеты" },
  { value: "day_time_profile", label: "Профили дня" },
  { value: "week_time_profile", label: "Профили недели" },
  { value: "user", label: "Пользователи" },
  { value: "schedule_import", label: "Импорт" },
];

type AuditEntry = {
  id: number;
  created_at: string;
  actor_name: string;
  actor_role: string;
  actor_role_label: string;
  entity_type: string;
  entity_label: string;
  action: string;
  summary: string;
};

type AuditPage = {
  items: AuditEntry[];
  total: number;
  limit: number;
  offset: number;
};

export default function AuditPage({ accessToken }: { accessToken: string }) {
  const [query, setQuery] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [entityType, setEntityType] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("Загрузка истории изменений.");
  const [busy, setBusy] = useState(false);
  // Filters change faster than requests come back; only the newest one may win.
  const requestRef = useRef(0);

  useEffect(() => {
    const timer = setTimeout(() => setSearchTerm(query.trim()), searchDebounceMs);
    return () => clearTimeout(timer);
  }, [query]);

  const load = useCallback(
    async (offset: number) => {
      const requestId = requestRef.current + 1;
      requestRef.current = requestId;
      setBusy(true);
      try {
        const params = new URLSearchParams({ limit: String(pageSize), offset: String(offset) });
        if (searchTerm) {
          params.set("q", searchTerm);
        }
        if (entityType !== "all") {
          params.set("entity_type", entityType);
        }
        if (dateFrom) {
          params.set("date_from", dateFrom);
        }
        if (dateTo) {
          params.set("date_to", dateTo);
        }
        const response = await fetch(`${apiBaseUrl}/audit?${params.toString()}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const page = (await response.json()) as AuditPage;
        if (requestId !== requestRef.current) {
          return;
        }
        setEntries((previous) => (offset === 0 ? page.items : [...previous, ...page.items]));
        setTotal(page.total);
        setStatus(page.total > 0 ? `Найдено записей: ${page.total}` : "Записей не найдено.");
      } catch {
        if (requestId === requestRef.current) {
          setStatus("Не удалось загрузить историю изменений.");
        }
      } finally {
        if (requestId === requestRef.current) {
          setBusy(false);
        }
      }
    },
    [accessToken, dateFrom, dateTo, entityType, searchTerm],
  );

  // load changes identity whenever a filter does, which restarts from the first page.
  useEffect(() => {
    void load(0);
  }, [load]);

  const hasMore = entries.length < total;

  return (
    <div className="audit-page">
      <div className="import-head">
        <div>
          <h1>История изменений</h1>
        </div>
        <div className="import-chip-row">
          <div className="import-chip">{total} записей</div>
        </div>
      </div>

      <div className="audit-toolbar">
        <label className="field audit-toolbar__search">
          <span>Поиск</span>
          <input
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Пользователь, кабинет, группа, действие"
            type="search"
            value={query}
          />
        </label>
        <label className="field audit-toolbar__date">
          <span>С</span>
          <input onChange={(event) => setDateFrom(event.target.value)} type="date" value={dateFrom} />
        </label>
        <label className="field audit-toolbar__date">
          <span>По</span>
          <input onChange={(event) => setDateTo(event.target.value)} type="date" value={dateTo} />
        </label>
        <button className="users-row__action" disabled={busy} onClick={() => load(0)} type="button">
          {busy ? "Загружаем..." : "Обновить"}
        </button>
      </div>

      <div className="problems-filters" aria-label="Фильтр по разделам">
        {entityFilters.map((filter) => (
          <button
            aria-pressed={entityType === filter.value}
            className={entityType === filter.value ? "problems-filter problems-filter--active" : "problems-filter"}
            key={filter.value}
            onClick={() => setEntityType(filter.value)}
            type="button"
          >
            <span>{filter.label}</span>
          </button>
        ))}
      </div>

      <div className="import-status">{status}</div>

      <div className="audit-list">
        {entries.length > 0 ? (
          entries.map((entry) => (
            <article className="audit-row" key={entry.id}>
              <div className="audit-row__time">{formatDateTime(entry.created_at)}</div>
              <div className="audit-row__body">
                <div className="audit-row__summary">{entry.summary}</div>
                <div className="audit-row__meta">
                  <span>{entry.actor_name}</span>
                  <span>{entry.actor_role_label}</span>
                </div>
              </div>
              <div className="audit-row__entity">{entry.entity_label}</div>
            </article>
          ))
        ) : (
          <div className="users-empty">{busy ? "Загрузка..." : "Записей по этому запросу не найдено."}</div>
        )}
      </div>

      {hasMore ? (
        <button
          className="users-row__action audit-more"
          disabled={busy}
          onClick={() => load(entries.length)}
          type="button"
        >
          {busy ? "Загружаем..." : `Показать ещё (${total - entries.length})`}
        </button>
      ) : null}
    </div>
  );
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${day}.${month}.${date.getFullYear()} ${hours}:${minutes}`;
}
