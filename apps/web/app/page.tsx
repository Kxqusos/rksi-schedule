"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, DragEvent, FormEvent } from "react";
import {
  CalendarDays,
  ClipboardList,
  DoorOpen,
  FileJson,
  History,
  ShieldCheck,
  UserRoundX,
  UsersRound,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

const primaryNav = [
  { label: "Расписание", icon: CalendarDays },
  { label: "Импорт JSON", icon: FileJson },
  { label: "История изменений", icon: History },
];

const operationsNav = [
  { label: "Отсутствующие преподаватели", icon: UserRoundX },
  { label: "Замены занятий", icon: ClipboardList },
  { label: "Свободные кабинеты", icon: DoorOpen },
];

const adminNav = [
  { label: "Пользователи и роли", icon: UsersRound },
  { label: "Аудит действий", icon: ShieldCheck },
];

const defaultSection = "Импорт JSON";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type AppRole = "admin" | "operator";

export default function Home() {
  const [activeSection, setActiveSection] = useState(defaultSection);
  const [currentRole, setCurrentRole] = useState<AppRole>("admin");
  const isWorkspacePage = activeSection === "Импорт JSON" || activeSection === "Пользователи и роли";

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Основная навигация">
        <div className="sidebar__brand">
          <div className="sidebar__mark" aria-hidden="true">
            R
          </div>
          <div>
            <div className="sidebar__title">RKSI Schedule</div>
            <div className="sidebar__caption">{currentRole}</div>
          </div>
        </div>

        <div className="role-switch" aria-label="Текущая роль">
          {(["admin", "operator"] as const).map((role) => (
            <button
              className={currentRole === role ? "role-switch__button role-switch__button--active" : "role-switch__button"}
              key={role}
              onClick={() => setCurrentRole(role)}
              type="button"
            >
              {role}
            </button>
          ))}
        </div>

        <nav className="sidebar__nav">
          <NavGroup
            activeSection={activeSection}
            items={primaryNav}
            onSelect={setActiveSection}
            title="Основное"
          />
          <NavGroup
            activeSection={activeSection}
            items={operationsNav}
            onSelect={setActiveSection}
            title="Операции"
          />
          <NavGroup
            activeSection={activeSection}
            items={adminNav}
            onSelect={setActiveSection}
            title="Администрирование"
          />
        </nav>
      </aside>

      <section
        className={isWorkspacePage ? "workspace workspace--import" : "workspace"}
        aria-label="Рабочая область"
      >
        {activeSection === "Импорт JSON" ? (
          <ImportPage />
        ) : activeSection === "Пользователи и роли" ? (
          <UsersPage currentRole={currentRole} />
        ) : (
          <div className="placeholder">
            <div className="placeholder__eyebrow">Раздел</div>
            <h1>{activeSection}</h1>
            <p>Раздел в разработке.</p>
          </div>
        )}
      </section>
    </main>
  );
}

type NavItem = {
  label: string;
  icon: LucideIcon;
};

function NavGroup({
  activeSection,
  items,
  onSelect,
  title,
}: {
  activeSection: string;
  items: NavItem[];
  onSelect: (section: string) => void;
  title: string;
}) {
  return (
    <div className="nav-group">
      <div className="nav-group__title">{title}</div>
      <div className="nav-group__items">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <button
              aria-current={activeSection === item.label ? "page" : undefined}
              className={activeSection === item.label ? "nav-item nav-item--active" : "nav-item"}
              key={item.label}
              onClick={() => onSelect(item.label)}
              type="button"
            >
              <Icon aria-hidden="true" className="nav-item__icon" size={18} strokeWidth={2} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function UsersPage({ currentRole }: { currentRole: AppRole }) {
  const [username, setUsername] = useState("");
  const [newUserRole, setNewUserRole] = useState<AppRole>("operator");
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [status, setStatus] = useState("Загрузка списка пользователей.");
  const [busy, setBusy] = useState<"load" | "create" | null>(null);

  const canManageUsers = currentRole === "admin";

  useEffect(() => {
    if (!canManageUsers) {
      setUsers([]);
      setStatus("Для управления пользователями нужна роль admin.");
      return;
    }

    let cancelled = false;
    const loadUsers = async () => {
      setBusy("load");
      try {
        const response = await fetch(`${apiBaseUrl}/users`, {
          headers: buildRoleHeaders(currentRole),
        });
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const result = (await response.json()) as UserRecord[];
        if (!cancelled) {
          setUsers(result);
          setStatus(result.length > 0 ? "Список пользователей загружен." : "Пользователей пока нет.");
        }
      } catch {
        if (!cancelled) {
          setStatus("Не удалось загрузить список пользователей.");
        }
      } finally {
        if (!cancelled) {
          setBusy(null);
        }
      }
    };

    void loadUsers();
    return () => {
      cancelled = true;
    };
  }, [canManageUsers, currentRole]);

  const createUser = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextUsername = username.trim();
    if (!nextUsername) {
      setStatus("Введите username.");
      return;
    }
    if (!canManageUsers) {
      setStatus("Создавать пользователей может только admin.");
      return;
    }

    setBusy("create");
    try {
      const response = await fetch(`${apiBaseUrl}/users`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...buildRoleHeaders(currentRole),
        },
        body: JSON.stringify({ username: nextUsername, role: newUserRole }),
      });

      if (response.status === 409) {
        setStatus("Пользователь с таким username уже есть.");
        return;
      }
      if (!response.ok) {
        throw new Error(await response.text());
      }

      const created = (await response.json()) as UserRecord;
      setUsers((currentUsers) => [...currentUsers, created]);
      setUsername("");
      setStatus(`Пользователь ${created.username} создан.`);
    } catch {
      setStatus("Не удалось создать пользователя.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="users-page">
      <div className="import-head">
        <div>
          <h1>Пользователи и роли</h1>
          <p>Создание пользователей доступно только роли admin.</p>
        </div>
        <div className="import-chip-row">
          <div className="import-chip">admin</div>
          <div className="import-chip">operator</div>
        </div>
      </div>

      <div className="users-grid">
        <form className="users-panel" onSubmit={createUser}>
          <div className="users-panel__title">Новый пользователь</div>
          <label className="field">
            <span>Username</span>
            <input
              disabled={!canManageUsers || busy !== null}
              maxLength={100}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="operator-1"
              value={username}
            />
          </label>
          <label className="field">
            <span>Роль</span>
            <select
              disabled={!canManageUsers || busy !== null}
              onChange={(event) => setNewUserRole(event.target.value as AppRole)}
              value={newUserRole}
            >
              <option value="operator">operator</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <button className="import-button import-button--primary" disabled={!canManageUsers || busy !== null} type="submit">
            {busy === "create" ? "Создаем..." : "Создать"}
          </button>
          <div className="import-status">{status}</div>
        </form>

        <div className="users-panel users-panel--list">
          <div className="users-panel__title">Список пользователей</div>
          {busy === "load" ? (
            <div className="users-empty">Загрузка...</div>
          ) : users.length > 0 ? (
            <div className="users-list">
              {users.map((user) => (
                <div className="users-row" key={user.id}>
                  <div>
                    <strong>{user.username}</strong>
                    <span>{formatDateTime(user.created_at)}</span>
                  </div>
                  <span className="users-role">{user.role}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="users-empty">{canManageUsers ? "Пользователей пока нет." : "Недоступно для operator."}</div>
          )}
        </div>
      </div>
    </div>
  );
}

type ImportSummary = {
  fileName: string;
  sizeBytes: number;
  timetableCount: number;
  groupCount: number;
  lessonCount: number;
  emptyDayCount: number;
  teacherCount: number;
  roomCount: number;
  subjectCount: number;
};

type UserRecord = {
  id: number;
  username: string;
  role: AppRole;
  created_at: string;
};

type ImportApiResult = {
  timetable_count: number;
  group_count: number;
  lesson_count: number;
  empty_day_count: number;
};

function ImportPage() {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewSummary, setPreviewSummary] = useState<ImportSummary | null>(null);
  const [uploadSummary, setUploadSummary] = useState<ImportSummary | null>(null);
  const [status, setStatus] = useState<string>("Выберите JSON-файл для загрузки.");
  const [busy, setBusy] = useState<"preview" | "upload" | null>(null);

  const fileMeta = useMemo(() => {
    if (!selectedFile) {
      return null;
    }
    return {
      name: selectedFile.name,
      size: formatBytes(selectedFile.size),
    };
  }, [selectedFile]);

  const openFilePicker = () => inputRef.current?.click();

  const setFile = (file: File | null) => {
    if (file && !file.name.toLowerCase().endsWith(".json")) {
      setSelectedFile(null);
      setUploadSummary(null);
      setPreviewSummary(null);
      setStatus("Выберите файл в формате JSON.");
      return;
    }

    setSelectedFile(file);
    setUploadSummary(null);
    setPreviewSummary(null);
    setStatus(file ? `Выбран файл ${file.name}` : "Выберите JSON-файл для загрузки.");
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    setFile(file);
  };

  const onDropFile = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setFile(event.dataTransfer.files?.[0] ?? null);
  };

  const parseSelectedFile = async () => {
    if (!selectedFile) {
      throw new Error("missing-file");
    }

    const text = await selectedFile.text();
    return summarizeSchedulePayload(JSON.parse(text), selectedFile.name, selectedFile.size);
  };

  const previewFile = async () => {
    if (!selectedFile) {
      setStatus("Сначала выберите JSON-файл.");
      return;
    }

    setBusy("preview");
    try {
      const summary = await parseSelectedFile();
      setPreviewSummary(summary);
      setStatus("Файл проверен локально.");
    } catch {
      setPreviewSummary(null);
      setStatus("Не удалось разобрать JSON-файл.");
    } finally {
      setBusy(null);
    }
  };

  const uploadFile = async () => {
    if (!selectedFile) {
      setStatus("Сначала выберите JSON-файл.");
      return;
    }

    setBusy("upload");
    try {
      const localSummary = previewSummary ?? (await parseSelectedFile());
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await fetch(`${apiBaseUrl}/imports/schedule`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const result = (await response.json()) as ImportApiResult;
      const summary: ImportSummary = {
        fileName: selectedFile.name,
        sizeBytes: selectedFile.size,
        timetableCount: result.timetable_count,
        groupCount: result.group_count,
        lessonCount: result.lesson_count,
        emptyDayCount: result.empty_day_count,
        teacherCount: localSummary.teacherCount,
        roomCount: localSummary.roomCount,
        subjectCount: localSummary.subjectCount,
      };
      setUploadSummary(summary);
      setPreviewSummary(summary);
      setStatus("Файл загружен в БД.");
    } catch {
      setStatus("Не удалось загрузить файл в БД.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="import-page">
      <div className="import-head">
        <div>
          <h1>Импорт JSON</h1>
          <p>Выберите файл, проверьте содержимое и загрузите расписание в БД.</p>
        </div>
        <div className="import-chip-row">
          <div className="import-chip">JSON</div>
          <div className="import-chip">Предпросмотр</div>
          <div className="import-chip">БД</div>
        </div>
      </div>

      <div className="import-panel">
        <input
          accept=".json,application/json"
          className="import-file-input"
          ref={inputRef}
          type="file"
          onChange={onFileChange}
        />

        <button
          className="import-dropzone"
          onClick={openFilePicker}
          onDragOver={(event) => event.preventDefault()}
          onDrop={onDropFile}
          type="button"
        >
          <strong>Загрузить JSON-файл</strong>
          <span>Нажмите для выбора или перетащите файл сюда.</span>
        </button>

        <div className="import-actions">
          <button className="import-button" disabled={!selectedFile || busy !== null} onClick={previewFile} type="button">
            {busy === "preview" ? "Проверяем..." : "Предпросмотр"}
          </button>
          <button
            className="import-button import-button--primary"
            disabled={!selectedFile || busy !== null}
            onClick={uploadFile}
            type="button"
          >
            {busy === "upload" ? "Загружаем..." : "Загрузить"}
          </button>
        </div>

        <div className="import-status">{status}</div>

        <div className="import-meta">
          <div className="import-card">
            <div className="import-card__label">Файл</div>
            <div className="import-card__value">{fileMeta ? fileMeta.name : "не выбран"}</div>
            <div className="import-card__hint">{fileMeta ? fileMeta.size : "выберите JSON для проверки и загрузки"}</div>
          </div>
          <ImportSummaryCard title="Предпросмотр" summary={previewSummary} />
          <ImportSummaryCard title="Загрузка в БД" summary={uploadSummary} />
        </div>
      </div>
    </div>
  );
}

function ImportSummaryCard({ title, summary }: { title: string; summary: ImportSummary | null }) {
  return (
    <div className="import-card">
      <div className="import-card__label">{title}</div>
      {summary ? (
        <div className="import-summary">
          <div className="import-summary__row">
            <span>Группы</span>
            <strong>{summary.groupCount}</strong>
          </div>
          <div className="import-summary__row">
            <span>Занятия</span>
            <strong>{summary.lessonCount}</strong>
          </div>
          <div className="import-summary__row">
            <span>Пустые дни</span>
            <strong>{summary.emptyDayCount}</strong>
          </div>
          <div className="import-summary__row">
            <span>Преподаватели</span>
            <strong>{summary.teacherCount}</strong>
          </div>
          <div className="import-summary__row">
            <span>Аудитории</span>
            <strong>{summary.roomCount}</strong>
          </div>
          <div className="import-summary__row">
            <span>Предметы</span>
            <strong>{summary.subjectCount}</strong>
          </div>
        </div>
      ) : (
        <div className="import-card__hint">Информация появится после предпросмотра или загрузки.</div>
      )}
    </div>
  );
}

function summarizeSchedulePayload(payload: unknown, fileName: string, sizeBytes: number): ImportSummary {
  const documents = Array.isArray(payload) ? payload : [payload];
  const groups = new Set<string>();
  const teachers = new Set<string>();
  const rooms = new Set<string>();
  const subjects = new Set<string>();

  let timetableCount = 0;
  let lessonCount = 0;
  let emptyDayCount = 0;

  for (const document of documents) {
    const timetable = getArray((document as Record<string, unknown> | null)?.timetable);
    timetableCount += timetable.length;

    for (const entry of timetable) {
      const groupList = getArray((entry as Record<string, unknown> | null)?.groups);

      for (const group of groupList) {
        const groupName = getString((group as Record<string, unknown> | null)?.group_name);
        if (groupName) {
          groups.add(groupName);
        }

        const dayList = getArray((group as Record<string, unknown> | null)?.days);
        for (const day of dayList) {
          const lessons = getArray((day as Record<string, unknown> | null)?.lessons);
          if (lessons.length === 0) {
            emptyDayCount += 1;
          }

          for (const lesson of lessons) {
            lessonCount += 1;
            const lessonSubject = getString((lesson as Record<string, unknown> | null)?.subject);
            if (lessonSubject) {
              subjects.add(lessonSubject);
            }

            const teacherList = getArray((lesson as Record<string, unknown> | null)?.teachers);
            for (const teacher of teacherList) {
              const teacherName = getString((teacher as Record<string, unknown> | null)?.teacher_name);
              if (teacherName) {
                teachers.add(teacherName);
              }
            }

            const roomList = getArray((lesson as Record<string, unknown> | null)?.auditories);
            for (const room of roomList) {
              const roomName = getString((room as Record<string, unknown> | null)?.auditory_name);
              if (roomName) {
                rooms.add(roomName);
              }
            }
          }
        }
      }
    }
  }

  return {
    fileName,
    sizeBytes,
    timetableCount,
    groupCount: groups.size,
    lessonCount,
    emptyDayCount,
    teacherCount: teachers.size,
    roomCount: rooms.size,
    subjectCount: subjects.size,
  };
}

function getArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function getString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  const kb = bytes / 1024;
  if (kb < 1024) {
    return `${kb.toFixed(kb >= 10 ? 0 : 1)} KB`;
  }

  return `${(kb / 1024).toFixed(1)} MB`;
}

function buildRoleHeaders(role: AppRole): HeadersInit {
  return {
    "X-Role": role,
    "X-Actor": role,
  };
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
