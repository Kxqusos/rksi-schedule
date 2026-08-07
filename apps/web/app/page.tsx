"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, DragEvent, FormEvent } from "react";
import {
  ClipboardList,
  Clock3,
  DoorOpen,
  FileJson,
  History,
  Trash2,
  TriangleAlert,
  UserRound,
  UsersRound,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import AuditPage from "./audit-page";

const primaryNav = [
  { label: "Импорт JSON", icon: FileJson },
  { label: "История изменений", icon: History },
];

const operationsNav = [
  { label: "Замены занятий", icon: ClipboardList },
  { label: "Проблемы", icon: TriangleAlert },
  { label: "Группы", icon: UsersRound },
  { label: "Кабинеты", icon: DoorOpen },
  { label: "Преподаватели", icon: UserRound },
  { label: "Профили времени", icon: Clock3 },
];

const adminNav = [
  { label: "Пользователи и роли", icon: UsersRound },
];

const defaultSection = "Замены занятий";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8001";
const lessonSlots = [1, 2, 3, 4, 5, 6, 7];
type AppRole = "admin" | "operator";
const tokenStorageKey = "schedule-rks.access-token";

type SessionUser = {
  id: number;
  username: string;
  display_name: string;
  role: AppRole;
  is_active: boolean;
  created_at: string;
};

type AuthSession = {
  accessToken: string;
  user: SessionUser;
};

export default function Home() {
  const [activeSection, setActiveSection] = useState(defaultSection);
  const [session, setSession] = useState<AuthSession | null>(null);
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    const token = window.localStorage.getItem(tokenStorageKey);
    if (!token) {
      setAuthReady(true);
      return;
    }

    let cancelled = false;
    const hydrateSession = async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/auth/me`, {
          headers: buildAuthHeaders(token),
        });
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const user = (await response.json()) as SessionUser;
        if (!cancelled) {
          setSession({ accessToken: token, user });
        }
      } catch {
        window.localStorage.removeItem(tokenStorageKey);
        if (!cancelled) {
          setSession(null);
        }
      } finally {
        if (!cancelled) {
          setAuthReady(true);
        }
      }
    };

    void hydrateSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLogin = (nextSession: AuthSession) => {
    window.localStorage.setItem(tokenStorageKey, nextSession.accessToken);
    setSession(nextSession);
    setActiveSection(defaultSection);
  };

  const handleLogout = () => {
    window.localStorage.removeItem(tokenStorageKey);
    setSession(null);
    setActiveSection(defaultSection);
  };

  if (!authReady) {
    return (
      <main className="auth-shell">
        <div className="auth-loader">Загрузка...</div>
      </main>
    );
  }

  if (!session) {
    return <LoginPage onLogin={handleLogin} />;
  }

  const isWorkspacePage =
    activeSection === "Замены занятий" ||
    activeSection === "Проблемы" ||
    activeSection === "Группы" ||
    activeSection === "Кабинеты" ||
    activeSection === "Преподаватели" ||
    activeSection === "Профили времени" ||
    activeSection === "Импорт JSON" ||
    activeSection === "История изменений" ||
    activeSection === "Пользователи и роли";

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Основная навигация">
        <div className="sidebar__brand">
          <div className="sidebar__mark" aria-hidden="true">
            R
          </div>
          <div>
            <div className="sidebar__title">RKSI Schedule</div>
            <div className="sidebar__caption">{session.user.display_name}</div>
          </div>
        </div>

        <div className="sidebar__session">
          <div>
            <div className="sidebar__session-role">{session.user.role}</div>
            <div className="sidebar__session-login">{session.user.username}</div>
          </div>
          <button className="sidebar__logout" onClick={handleLogout} type="button">
            Выйти
          </button>
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
        {activeSection === "Замены занятий" ? (
          <SchedulePage accessToken={session.accessToken} />
        ) : activeSection === "Проблемы" ? (
          <ProblemsPage accessToken={session.accessToken} />
        ) : activeSection === "Группы" ? (
          <GroupsPage accessToken={session.accessToken} />
        ) : activeSection === "Кабинеты" ? (
          <RoomsPage accessToken={session.accessToken} />
        ) : activeSection === "Преподаватели" ? (
          <TeachersPage accessToken={session.accessToken} />
        ) : activeSection === "Профили времени" ? (
          <TimeProfilesPage accessToken={session.accessToken} />
        ) : activeSection === "Импорт JSON" ? (
          <ImportPage accessToken={session.accessToken} />
        ) : activeSection === "История изменений" ? (
          <AuditPage accessToken={session.accessToken} />
        ) : activeSection === "Пользователи и роли" ? (
          <UsersPage currentUser={session.user} accessToken={session.accessToken} />
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

function LoginPage({ onLogin }: { onLogin: (session: AuthSession) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("Введите логин и пароль.");
  const [busy, setBusy] = useState(false);

  const login = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextUsername = username.trim();
    if (!nextUsername || !password) {
      setStatus("Введите логин и пароль.");
      return;
    }

    setBusy(true);
    try {
      const response = await fetch(`${apiBaseUrl}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: nextUsername, password }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as { access_token: string; user: SessionUser };
      onLogin({ accessToken: payload.access_token, user: payload.user });
    } catch {
      setStatus("Не удалось войти.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-shell">
      <form className="auth-card" onSubmit={login}>
        <div className="auth-card__eyebrow">RKSI Schedule</div>
        <h1>Вход</h1>
        <label className="field">
          <span>Логин</span>
          <input disabled={busy} onChange={(event) => setUsername(event.target.value)} value={username} />
        </label>
        <label className="field">
          <span>Пароль</span>
          <input disabled={busy} onChange={(event) => setPassword(event.target.value)} type="password" value={password} />
        </label>
        <button className="import-button import-button--primary" disabled={busy} type="submit">
          {busy ? "Входим..." : "Войти"}
        </button>
        <div className="import-status">{status}</div>
      </form>
    </main>
  );
}

function UsersPage({ accessToken, currentUser }: { accessToken: string; currentUser: SessionUser }) {
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [newUserRole, setNewUserRole] = useState<AppRole>("operator");
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [selectedUser, setSelectedUser] = useState<UserRecord | null>(null);
  const [selectedCredentials, setSelectedCredentials] = useState<UserRecord | null>(null);
  const [passwordDraft, setPasswordDraft] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [passwordEditorOpen, setPasswordEditorOpen] = useState(false);
  const [status, setStatus] = useState("Загрузка списка пользователей.");
  const [busy, setBusy] = useState<"load" | "create" | "password" | null>(null);

  const canManageUsers = currentUser.role === "admin";

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
          headers: buildAuthHeaders(accessToken),
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
  }, [accessToken, canManageUsers]);

  const createUser = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextUsername = username.trim();
    if (!nextUsername) {
      setStatus("Введите username.");
      return;
    }
    if (!displayName.trim()) {
      setStatus("Введите отображаемое имя.");
      return;
    }
    if (password.length < 8) {
      setStatus("Пароль должен быть не короче 8 символов.");
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
          ...buildAuthHeaders(accessToken),
        },
        body: JSON.stringify({
          username: nextUsername,
          display_name: displayName.trim(),
          password,
          role: newUserRole,
        }),
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
      setDisplayName("");
      setPassword("");
      setStatus(`Пользователь ${created.username} создан.`);
    } catch {
      setStatus("Не удалось создать пользователя.");
    } finally {
      setBusy(null);
    }
  };

  const loadCredentials = async (user: UserRecord) => {
    setSelectedUser(user);
    setPasswordDraft("");
    setPasswordConfirm("");
    setPasswordEditorOpen(false);
    setStatus("Загрузка данных пользователя.");
    try {
      const response = await fetch(`${apiBaseUrl}/users/${user.id}/credentials`, {
        headers: buildAuthHeaders(accessToken),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as UserRecord;
      setSelectedCredentials(payload);
      setStatus("Данные пользователя загружены.");
    } catch {
      setSelectedCredentials(null);
      setStatus("Не удалось загрузить данные пользователя.");
    }
  };

  const openPasswordEditor = () => {
    setPasswordDraft("");
    setPasswordConfirm("");
    setPasswordEditorOpen(true);
    setStatus("Введите новый пароль.");
  };

  const changePassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedCredentials) {
      setStatus("Сначала выберите пользователя.");
      return;
    }
    if (passwordDraft.length < 8) {
      setStatus("Пароль должен быть не короче 8 символов.");
      return;
    }
    if (passwordDraft !== passwordConfirm) {
      setStatus("Пароли не совпадают.");
      return;
    }

    setBusy("password");
    try {
      const response = await fetch(`${apiBaseUrl}/users/${selectedCredentials.id}/password`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...buildAuthHeaders(accessToken),
        },
        body: JSON.stringify({ password: passwordDraft }),
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const updated = (await response.json()) as UserRecord;
      setUsers((currentUsers) => currentUsers.map((item) => (item.id === updated.id ? updated : item)));
      setSelectedCredentials(updated);
      setSelectedUser(updated);
      setPasswordDraft("");
      setPasswordConfirm("");
      setPasswordEditorOpen(false);
      setStatus(`Пароль пользователя ${updated.username} изменён.`);
    } catch {
      setStatus("Не удалось сменить пароль.");
    } finally {
      setBusy(null);
    }
  };

  const revokeUser = async (user: UserRecord) => {
    if (!window.confirm(`Отозвать доступ пользователя ${user.username}?`)) {
      return;
    }

    setBusy("load");
    try {
      const response = await fetch(`${apiBaseUrl}/users/${user.id}/revoke`, {
        method: "POST",
        headers: buildAuthHeaders(accessToken),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const updated = (await response.json()) as UserRecord;
      setUsers((currentUsers) => currentUsers.map((item) => (item.id === updated.id ? updated : item)));
      if (selectedUser?.id === updated.id) {
        setSelectedUser(updated);
        setSelectedCredentials(updated);
      }
      setStatus(`Пользователь ${updated.username} отозван.`);
    } catch {
      setStatus("Не удалось отозвать пользователя.");
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
            <span>Логин</span>
            <input
              disabled={!canManageUsers || busy !== null}
              maxLength={100}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="operator-1"
              value={username}
            />
          </label>
          <label className="field">
            <span>Отображаемое имя</span>
            <input
              disabled={!canManageUsers || busy !== null}
              maxLength={150}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Оператор 1"
              value={displayName}
            />
          </label>
          <label className="field">
            <span>Пароль</span>
            <input
              disabled={!canManageUsers || busy !== null}
              maxLength={128}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              type="password"
              value={password}
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

        <div className="users-panel users-panel--credentials">
          <div className="users-panel__title">Список пользователей</div>
          {busy === "load" ? (
            <div className="users-empty">Загрузка...</div>
          ) : users.length > 0 ? (
            <div className="users-list">
              {users.map((user) => (
                <div className="users-row" key={user.id}>
                  <div className="users-row__body">
                    <strong>{user.display_name}</strong>
                    <span className="users-row__login">@{user.username}</span>
                    <span>{formatDateTime(user.created_at)}</span>
                  </div>
                  <div className="users-row__side">
                    <span className={user.is_active ? "users-role users-role--active" : "users-role users-role--inactive"}>
                      {user.role}
                    </span>
                    <div className="users-row__actions">
                      <button className="users-row__action" onClick={() => loadCredentials(user)} type="button">
                        Креды
                      </button>
                      <button
                        className="users-row__action"
                        disabled={!user.is_active || busy !== null}
                        onClick={() => revokeUser(user)}
                        type="button"
                      >
                        Отозвать
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="users-empty">{canManageUsers ? "Пользователей пока нет." : "Недоступно для operator."}</div>
          )}
        </div>

        <div className="users-panel users-panel--list">
          <div className="users-panel__title">Креды пользователя</div>
          {selectedCredentials ? (
            <div className="users-credentials">
              <div className="users-credentials__row">
                <span>Логин</span>
                <strong>{selectedCredentials.username}</strong>
              </div>
              <div className="users-credentials__row">
                <span>Отображаемое имя</span>
                <strong>{selectedCredentials.display_name}</strong>
              </div>
              <div className="users-credentials__row">
                <span>Роль</span>
                <strong>{selectedCredentials.role}</strong>
              </div>
              <div className="users-credentials__row">
                <span>Статус</span>
                <strong>{selectedCredentials.is_active ? "активен" : "отозван"}</strong>
              </div>
              <div className="users-credentials__actions">
                <button className="users-row__action" disabled={busy !== null} onClick={openPasswordEditor} type="button">
                  Сменить пароль
                </button>
              </div>
              {passwordEditorOpen ? (
                <form className="users-password-form" onSubmit={changePassword}>
                  <label className="field">
                    <span>Новый пароль</span>
                    <input
                      disabled={busy !== null}
                      maxLength={128}
                      onChange={(event) => setPasswordDraft(event.target.value)}
                      type="password"
                      value={passwordDraft}
                    />
                  </label>
                  <label className="field">
                    <span>Повтор пароля</span>
                    <input
                      disabled={busy !== null}
                      maxLength={128}
                      onChange={(event) => setPasswordConfirm(event.target.value)}
                      type="password"
                      value={passwordConfirm}
                    />
                  </label>
                  <div className="users-password-form__actions">
                    <button className="users-row__action" disabled={busy !== null} onClick={() => setPasswordEditorOpen(false)} type="button">
                      Отмена
                    </button>
                    <button className="import-button import-button--primary" disabled={busy !== null} type="submit">
                      {busy === "password" ? "Сохраняем..." : "Сменить"}
                    </button>
                  </div>
                </form>
              ) : null}
            </div>
          ) : (
            <div className="users-empty">Выберите пользователя, чтобы посмотреть данные.</div>
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
  display_name: string;
  role: AppRole;
  is_active: boolean;
  created_at: string;
};

type RoomRecord = {
  id: number;
  name: string;
  building: string;
  lesson_count: number;
  is_excluded: boolean;
  exclusion_reason: string;
};

type TeacherRecord = {
  id: number;
  teacher_id: string;
  name: string;
  post: string;
  lesson_count: number;
  absences: TeacherAbsenceRecord[];
};

type GroupRecord = {
  id: number;
  name: string;
  course: number;
  faculty: string;
  lesson_count: number;
  homeroom_teacher_id: number | null;
  homeroom_teacher_name: string | null;
};

type TeacherAbsenceRecord = {
  id: number;
  date: string;
  all_day: boolean;
  time_slot_start: number | null;
  time_slot_end: number | null;
  reason: string;
};

type DayTimeProfileSlot = {
  slot_number: number;
  time_start: string;
  time_end: string;
};

type DayTimeProfile = {
  id: number;
  name: string;
  created_at: string;
  slots: DayTimeProfileSlot[];
};

type WeekTimeProfileDay = {
  weekday: number;
  day_profile_id: number;
  day_profile_name: string;
};

type WeekTimeProfile = {
  id: number;
  name: string;
  created_at: string;
  days: WeekTimeProfileDay[];
};

type ScheduleProblem = {
  severity: "error" | "warning";
  code: string;
  message: string;
  date: string | null;
  week_number: number | null;
  time_slot: number | null;
  group_name: string | null;
  teacher_name: string | null;
  room_name: string | null;
  lesson_ids: number[];
};

type LessonMutationResponse = LessonRecord & {
  warnings?: ScheduleProblem[];
};

const problemFilterLabels: Record<string, string> = {
  all: "Все",
  group_week_limit_exceeded: "Группы >18 пар",
  group_day_limit_exceeded: "Группы >4 пар в день",
  group_day_minimum_not_met: "Группы <2 пар в день",
  group_day_window: "Окна у групп",
  group_slot_multiple_teachers: "2 преподавателя у группы",
  teacher_double_booked: "Преподаватель на 2 группы",
  room_double_booked: "Кабинет на 2 группы",
  absent_teacher_scheduled: "Отсутствующие преподаватели",
  excluded_room_scheduled: "Исключённые кабинеты",
};

const defaultProblemFilterCodes = [
  "group_week_limit_exceeded",
  "group_day_limit_exceeded",
  "group_day_minimum_not_met",
  "group_day_window",
  "group_slot_multiple_teachers",
  "teacher_double_booked",
  "room_double_booked",
  "absent_teacher_scheduled",
  "excluded_room_scheduled",
];

function ProblemsPage({ accessToken }: { accessToken: string }) {
  const [problems, setProblems] = useState<ScheduleProblem[]>([]);
  const [activeFilter, setActiveFilter] = useState("all");
  const [status, setStatus] = useState("Загрузка списка проблем.");
  const [busy, setBusy] = useState(false);

  const loadProblems = async () => {
    setBusy(true);
    try {
      const response = await fetch(`${apiBaseUrl}/schedule/problems`, {
        headers: buildAuthHeaders(accessToken),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const result = (await response.json()) as ScheduleProblem[];
      setProblems(result);
      setStatus(result.length > 0 ? "Проверка расписания выполнена." : "Проблем не найдено.");
    } catch {
      setStatus("Не удалось загрузить проблемы расписания.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadProblems();
  }, [accessToken]);

  const errorCount = problems.filter((problem) => problem.severity === "error").length;
  const warningCount = problems.filter((problem) => problem.severity === "warning").length;
  const problemFilterOptions = useMemo(() => buildProblemFilterOptions(problems), [problems]);
  const filteredProblems = useMemo(
    () => (activeFilter === "all" ? problems : problems.filter((problem) => problem.code === activeFilter)),
    [activeFilter, problems],
  );

  useEffect(() => {
    if (activeFilter === "all") {
      return;
    }
    if (!problemFilterOptions.some((option) => option.code === activeFilter)) {
      setActiveFilter("all");
    }
  }, [activeFilter, problemFilterOptions]);

  return (
    <div className="problems-page">
      <div className="import-head">
        <div>
          <h1>Проблемы</h1>
        </div>
        <div className="import-chip-row">
          <div className="import-chip">{errorCount} ошибок</div>
          <div className="import-chip">{warningCount} предупреждений</div>
        </div>
      </div>

      <div className="problems-toolbar">
        <div className="import-status">{status}</div>
        <button className="users-row__action" disabled={busy} onClick={loadProblems} type="button">
          {busy ? "Проверяем..." : "Обновить"}
        </button>
      </div>

      <div className="problems-filters" aria-label="Фильтр проблем">
        {problemFilterOptions.map((option) => (
          <button
            aria-pressed={activeFilter === option.code}
            className={activeFilter === option.code ? "problems-filter problems-filter--active" : "problems-filter"}
            key={option.code}
            onClick={() => setActiveFilter(option.code)}
            type="button"
          >
            <span>{option.label}</span>
            <strong>{option.count}</strong>
          </button>
        ))}
      </div>

      <div className="problems-list">
        {filteredProblems.length > 0 ? (
          filteredProblems.map((problem, index) => (
            <article
              className={problem.severity === "error" ? "problem-card problem-card--error" : "problem-card problem-card--warning"}
              key={`${problem.code}-${problem.date ?? "week"}-${problem.time_slot ?? 0}-${index}`}
            >
              <div className="problem-card__head">
                <span>{problem.severity === "error" ? "Ошибка" : "Предупреждение"}</span>
                <strong>{problem.code}</strong>
              </div>
              <div className="problem-card__message">{problem.message}</div>
              <div className="problem-card__meta">
                {problem.date ? <span>{formatPlainDate(problem.date)}</span> : null}
                {problem.week_number ? <span>{problem.week_number} неделя</span> : null}
                {problem.time_slot ? <span>{problem.time_slot} пара</span> : null}
                {problem.group_name ? <span>{problem.group_name}</span> : null}
                {problem.teacher_name ? <span>{problem.teacher_name}</span> : null}
                {problem.room_name ? <span>{problem.room_name}</span> : null}
              </div>
            </article>
          ))
        ) : (
          <div className="users-empty">{busy ? "Загрузка..." : "Проблем по этому фильтру не найдено."}</div>
        )}
      </div>
    </div>
  );
}

function GroupsPage({ accessToken }: { accessToken: string }) {
  const [groups, setGroups] = useState<GroupRecord[]>([]);
  const [teachers, setTeachers] = useState<TeacherRecord[]>([]);
  const [editingGroup, setEditingGroup] = useState<GroupRecord | null>(null);
  const [editGroupName, setEditGroupName] = useState("");
  const [editTeacherId, setEditTeacherId] = useState("");
  const [status, setStatus] = useState("Загрузка списка групп.");
  const [busy, setBusy] = useState<"load" | "save" | "delete" | null>(null);

  useEffect(() => {
    let cancelled = false;
    const loadGroups = async () => {
      setBusy("load");
      try {
        const [groupsResponse, teachersResponse] = await Promise.all([
          fetch(`${apiBaseUrl}/groups`, { headers: buildAuthHeaders(accessToken) }),
          fetch(`${apiBaseUrl}/teachers`, { headers: buildAuthHeaders(accessToken) }),
        ]);
        if (!groupsResponse.ok || !teachersResponse.ok) {
          throw new Error("failed to load groups");
        }
        const nextGroups = (await groupsResponse.json()) as GroupRecord[];
        const nextTeachers = (await teachersResponse.json()) as TeacherRecord[];
        if (!cancelled) {
          setGroups(nextGroups.sort(compareGroups));
          setTeachers(nextTeachers.sort(compareTeachers));
          setStatus(nextGroups.length > 0 ? "Список групп загружен." : "Групп пока нет.");
        }
      } catch {
        if (!cancelled) {
          setStatus("Не удалось загрузить список групп.");
        }
      } finally {
        if (!cancelled) {
          setBusy(null);
        }
      }
    };

    void loadGroups();
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  useEffect(() => {
    if (!editingGroup) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && busy !== "save") {
        setEditingGroup(null);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, editingGroup]);

  const openGroupEditor = (group: GroupRecord) => {
    setEditingGroup(group);
    setEditGroupName(group.name);
    setEditTeacherId(group.homeroom_teacher_id ? String(group.homeroom_teacher_id) : "");
  };

  const saveGroup = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editingGroup) {
      return;
    }
    const name = editGroupName.trim();
    if (!name) {
      setStatus("Введите название группы.");
      return;
    }

    setBusy("save");
    try {
      const renameResponse = await fetch(`${apiBaseUrl}/groups/${editingGroup.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...buildAuthHeaders(accessToken),
        },
        body: JSON.stringify({ name }),
      });
      if (renameResponse.status === 409) {
        setStatus("Группа с таким названием уже есть.");
        return;
      }
      if (!renameResponse.ok) {
        throw new Error(await renameResponse.text());
      }

      const teacherResponse = await fetch(`${apiBaseUrl}/groups/${editingGroup.id}/homeroom-teacher`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...buildAuthHeaders(accessToken),
        },
        body: JSON.stringify({ teacher_id: editTeacherId ? Number(editTeacherId) : null }),
      });
      if (!teacherResponse.ok) {
        throw new Error(await teacherResponse.text());
      }
      const updated = (await teacherResponse.json()) as GroupRecord;
      setGroups((currentGroups) => currentGroups.map((group) => (group.id === updated.id ? updated : group)).sort(compareGroups));
      setEditingGroup(null);
      setStatus(`Группа ${updated.name} обновлена.`);
    } catch {
      setStatus("Не удалось сохранить группу.");
    } finally {
      setBusy(null);
    }
  };

  const deleteGroup = async (group: GroupRecord) => {
    const suffix = group.lesson_count > 0 ? ` Будет удалено занятий: ${group.lesson_count}.` : "";
    if (!window.confirm(`Удалить группу ${group.name}?${suffix}`)) {
      return;
    }

    setBusy("delete");
    try {
      const response = await fetch(`${apiBaseUrl}/groups/${group.id}`, {
        method: "DELETE",
        headers: buildAuthHeaders(accessToken),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      setGroups((currentGroups) => currentGroups.filter((item) => item.id !== group.id));
      setEditingGroup((currentGroup) => (currentGroup?.id === group.id ? null : currentGroup));
      setStatus(`Группа ${group.name} удалена.`);
    } catch {
      setStatus("Не удалось удалить группу.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="groups-page">
      <div className="import-head">
        <div>
          <h1>Группы</h1>
        </div>
        <div className="import-chip-row">
          <div className="import-chip">{groups.length} всего</div>
          <div className="import-chip">Классные руководители</div>
        </div>
      </div>

      <div className="groups-list">
        {busy === "load" ? (
          <div className="users-empty">Загрузка...</div>
        ) : groups.length > 0 ? (
          <div className="rooms-card-list">
            {groups.map((group) => (
              <div className="rooms-row" key={group.id}>
                <div className="rooms-row__body">
                  <strong>{group.name}</strong>
                  <span>
                    {group.course ? `${group.course} курс` : "Курс не указан"}
                    {group.faculty ? ` · ${group.faculty}` : ""}
                  </span>
                  <span>{group.lesson_count} занятий</span>
                  <span>{group.homeroom_teacher_name ? `Классный руководитель: ${group.homeroom_teacher_name}` : "Классный руководитель не назначен"}</span>
                </div>
                <div className="rooms-row-actions">
                  <button className="users-row__action" disabled={busy !== null} onClick={() => openGroupEditor(group)} type="button">
                    Изменить
                  </button>
                  <button
                    aria-label={`Удалить группу ${group.name}`}
                    className="users-row__action rooms-row__delete"
                    disabled={busy !== null}
                    onClick={() => deleteGroup(group)}
                    title="Удалить"
                    type="button"
                  >
                    <Trash2 aria-hidden="true" size={15} strokeWidth={2} />
                    <span>Удалить</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="users-empty">Групп пока нет.</div>
        )}
      </div>
      <div className="import-status">{status}</div>

      {editingGroup ? (
        <div className="teachers-modal" role="dialog" aria-modal="true" aria-labelledby="group-edit-title">
          <button
            aria-label="Закрыть меню группы"
            className="teachers-modal__backdrop"
            disabled={busy === "save"}
            onClick={() => setEditingGroup(null)}
            type="button"
          />
          <form className="teachers-absence-dialog" onSubmit={saveGroup}>
            <div className="schedule-edit__section-head">
              <span>Группа</span>
            </div>
            <div className="teachers-absence-dialog__title" id="group-edit-title">
              {editingGroup.name}
            </div>
            <label className="field">
              <span>Название</span>
              <input
                disabled={busy !== null}
                maxLength={100}
                onChange={(event) => setEditGroupName(event.target.value)}
                value={editGroupName}
              />
            </label>
            <label className="field">
              <span>Классный руководитель</span>
              <select disabled={busy !== null} onChange={(event) => setEditTeacherId(event.target.value)} value={editTeacherId}>
                <option value="">Не назначен</option>
                {teachers.map((teacher) => (
                  <option key={teacher.id} value={teacher.id}>
                    {teacher.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="schedule-edit__actions">
              <button className="users-row__action" disabled={busy === "save"} onClick={() => setEditingGroup(null)} type="button">
                Отмена
              </button>
              <button className="import-button import-button--primary" disabled={busy !== null} type="submit">
                {busy === "save" ? "Сохраняем..." : "Сохранить"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}

function RoomsPage({ accessToken }: { accessToken: string }) {
  const [rooms, setRooms] = useState<RoomRecord[]>([]);
  const [roomName, setRoomName] = useState("");
  const [exclusionRoom, setExclusionRoom] = useState<RoomRecord | null>(null);
  const [exclusionReason, setExclusionReason] = useState("");
  const [status, setStatus] = useState("Загрузка списка кабинетов.");
  const [busy, setBusy] = useState<"load" | "create" | "delete" | "exclusion" | null>(null);

  useEffect(() => {
    let cancelled = false;
    const loadRooms = async () => {
      setBusy("load");
      try {
        const response = await fetch(`${apiBaseUrl}/rooms`, {
          headers: buildAuthHeaders(accessToken),
        });
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const result = (await response.json()) as RoomRecord[];
        if (!cancelled) {
          setRooms(result);
          setStatus(result.length > 0 ? "Список кабинетов загружен." : "Кабинетов пока нет.");
        }
      } catch {
        if (!cancelled) {
          setStatus("Не удалось загрузить список кабинетов.");
        }
      } finally {
        if (!cancelled) {
          setBusy(null);
        }
      }
    };

    void loadRooms();
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  const groupedRooms = useMemo(() => groupRoomsByBuilding(rooms), [rooms]);

  useEffect(() => {
    if (!exclusionRoom) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && busy !== "exclusion") {
        setExclusionRoom(null);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, exclusionRoom]);

  const createRoom = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextName = roomName.trim();
    if (!nextName) {
      setStatus("Введите название кабинета.");
      return;
    }

    setBusy("create");
    try {
      const response = await fetch(`${apiBaseUrl}/rooms`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...buildAuthHeaders(accessToken),
        },
        body: JSON.stringify({ name: nextName }),
      });

      if (response.status === 409) {
        setStatus("Кабинет с таким названием уже есть.");
        return;
      }
      if (!response.ok) {
        throw new Error(await response.text());
      }

      const created = (await response.json()) as RoomRecord;
      setRooms((currentRooms) => [...currentRooms, created].sort(compareRooms));
      setRoomName("");
      setStatus(`Кабинет ${created.name} добавлен.`);
    } catch {
      setStatus("Не удалось добавить кабинет.");
    } finally {
      setBusy(null);
    }
  };

  const deleteRoom = async (room: RoomRecord) => {
    const suffix = room.lesson_count > 0 ? ` ${room.lesson_count} занятий останутся без кабинета.` : "";
    if (!window.confirm(`Удалить кабинет ${room.name}?${suffix}`)) {
      return;
    }

    setBusy("delete");
    try {
      const response = await fetch(`${apiBaseUrl}/rooms/${room.id}`, {
        method: "DELETE",
        headers: buildAuthHeaders(accessToken),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      setRooms((currentRooms) => currentRooms.filter((item) => item.id !== room.id));
      setStatus(`Кабинет ${room.name} удалён.`);
    } catch {
      setStatus("Не удалось удалить кабинет.");
    } finally {
      setBusy(null);
    }
  };

  const openExclusionDialog = (room: RoomRecord) => {
    setExclusionRoom(room);
    setExclusionReason(room.exclusion_reason);
  };

  const excludeRoom = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!exclusionRoom) {
      setStatus("Выберите кабинет.");
      return;
    }

    setBusy("exclusion");
    try {
      const response = await fetch(`${apiBaseUrl}/rooms/${exclusionRoom.id}/exclusion`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...buildAuthHeaders(accessToken),
        },
        body: JSON.stringify({ reason: exclusionReason.trim() }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const updated = (await response.json()) as RoomRecord;
      setRooms((currentRooms) => currentRooms.map((room) => (room.id === updated.id ? updated : room)));
      setExclusionRoom(null);
      setExclusionReason("");
      setStatus(`Кабинет ${updated.name} исключён из расписания.`);
    } catch {
      setStatus("Не удалось исключить кабинет.");
    } finally {
      setBusy(null);
    }
  };

  const restoreRoom = async (room: RoomRecord) => {
    setBusy("exclusion");
    try {
      const response = await fetch(`${apiBaseUrl}/rooms/${room.id}/exclusion`, {
        method: "DELETE",
        headers: buildAuthHeaders(accessToken),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const updated = (await response.json()) as RoomRecord;
      setRooms((currentRooms) => currentRooms.map((currentRoom) => (currentRoom.id === updated.id ? updated : currentRoom)));
      setStatus(`Кабинет ${updated.name} возвращён в расписание.`);
    } catch {
      setStatus("Не удалось вернуть кабинет.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="rooms-page">
      <div className="import-head">
        <div>
          <h1>Кабинеты</h1>
        </div>
        <div className="import-chip-row">
          <div className="import-chip">{rooms.length} всего</div>
          <div className="import-chip">Корпуса</div>
        </div>
      </div>

      <div className="rooms-grid">
        <form className="users-panel rooms-create" onSubmit={createRoom}>
          <div className="users-panel__title">Новый кабинет</div>
          <label className="field">
            <span>Название</span>
            <input
              disabled={busy !== null}
              maxLength={100}
              onChange={(event) => setRoomName(event.target.value)}
              placeholder="999/3"
              value={roomName}
            />
          </label>
          <button className="import-button import-button--primary" disabled={busy !== null} type="submit">
            {busy === "create" ? "Добавляем..." : "Добавить"}
          </button>
          <div className="import-status">{status}</div>
        </form>

        <div className="rooms-list">
          {busy === "load" ? (
            <div className="users-empty">Загрузка...</div>
          ) : groupedRooms.length > 0 ? (
            groupedRooms.map((group) => (
              <section className="rooms-building" key={group.building}>
                <div className="schedule-building__head">
                  <h2>{group.building}</h2>
                  <span>{group.rooms.length} кабинетов</span>
                </div>
                <div className="rooms-card-list">
                  {group.rooms.map((room) => (
                    <div className={room.is_excluded ? "rooms-row rooms-row--excluded" : "rooms-row"} key={room.id}>
                      <div className="rooms-row__body">
                        <strong>{room.name}</strong>
                        <span>{room.lesson_count} занятий</span>
                        {room.is_excluded ? (
                          <div className="rooms-exclusion">
                            <span className="rooms-exclusion__badge">Исключён</span>
                            {room.exclusion_reason ? <span>{room.exclusion_reason}</span> : null}
                          </div>
                        ) : null}
                      </div>
                      <div className="rooms-row-actions">
                        {room.is_excluded ? (
                          <button className="users-row__action" disabled={busy !== null} onClick={() => restoreRoom(room)} type="button">
                            Вернуть
                          </button>
                        ) : (
                          <button className="users-row__action" disabled={busy !== null} onClick={() => openExclusionDialog(room)} type="button">
                            Исключить
                          </button>
                        )}
                        <button
                          aria-label={`Удалить кабинет ${room.name}`}
                          className="users-row__action rooms-row__delete"
                          disabled={busy !== null}
                          onClick={() => deleteRoom(room)}
                          title="Удалить"
                          type="button"
                        >
                          <Trash2 aria-hidden="true" size={15} strokeWidth={2} />
                          <span>Удалить</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ))
          ) : (
            <div className="users-empty">Кабинетов пока нет.</div>
          )}
        </div>
      </div>
      {exclusionRoom ? (
        <div className="teachers-modal" role="dialog" aria-modal="true" aria-labelledby="room-exclusion-title">
          <button
            aria-label="Закрыть меню исключения кабинета"
            className="teachers-modal__backdrop"
            disabled={busy === "exclusion"}
            onClick={() => setExclusionRoom(null)}
            type="button"
          />
          <form className="teachers-absence-dialog" onSubmit={excludeRoom}>
            <div className="schedule-edit__section-head">
              <span>Исключение кабинета</span>
            </div>
            <div className="teachers-absence-dialog__title" id="room-exclusion-title">
              {exclusionRoom.name}
            </div>
            <label className="field">
              <span>Причина</span>
              <input
                disabled={busy !== null}
                maxLength={300}
                onChange={(event) => setExclusionReason(event.target.value)}
                placeholder="необязательно"
                value={exclusionReason}
              />
            </label>
            <div className="schedule-edit__actions">
              <button className="users-row__action" disabled={busy === "exclusion"} onClick={() => setExclusionRoom(null)} type="button">
                Отмена
              </button>
              <button className="import-button import-button--primary" disabled={busy !== null} type="submit">
                {busy === "exclusion" ? "Сохраняем..." : "Исключить"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}

function TeachersPage({ accessToken }: { accessToken: string }) {
  const [teachers, setTeachers] = useState<TeacherRecord[]>([]);
  const [teacherName, setTeacherName] = useState("");
  const [teacherId, setTeacherId] = useState("");
  const [teacherPost, setTeacherPost] = useState("");
  const [absenceTeacher, setAbsenceTeacher] = useState<TeacherRecord | null>(null);
  const [absenceDate, setAbsenceDate] = useState(toLocalDateInput(new Date()));
  const [absenceSlots, setAbsenceSlots] = useState<number[]>(lessonSlots);
  const [absenceReason, setAbsenceReason] = useState("");
  const [status, setStatus] = useState("Загрузка списка преподавателей.");
  const [busy, setBusy] = useState<"load" | "create" | "delete" | "absence" | null>(null);

  useEffect(() => {
    let cancelled = false;
    const loadTeachers = async () => {
      setBusy("load");
      try {
        const response = await fetch(`${apiBaseUrl}/teachers`, {
          headers: buildAuthHeaders(accessToken),
        });
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const result = (await response.json()) as TeacherRecord[];
        if (!cancelled) {
          setTeachers(result);
          setStatus(result.length > 0 ? "Список преподавателей загружен." : "Преподавателей пока нет.");
        }
      } catch {
        if (!cancelled) {
          setStatus("Не удалось загрузить список преподавателей.");
        }
      } finally {
        if (!cancelled) {
          setBusy(null);
        }
      }
    };

    void loadTeachers();
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  const createTeacher = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextName = teacherName.trim();
    if (!nextName) {
      setStatus("Введите имя преподавателя.");
      return;
    }

    setBusy("create");
    try {
      const response = await fetch(`${apiBaseUrl}/teachers`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...buildAuthHeaders(accessToken),
        },
        body: JSON.stringify({
          name: nextName,
          teacher_id: teacherId.trim() || null,
          post: teacherPost.trim(),
        }),
      });

      if (response.status === 409) {
        setStatus("Преподаватель с таким идентификатором уже есть.");
        return;
      }
      if (!response.ok) {
        throw new Error(await response.text());
      }

      const created = (await response.json()) as TeacherRecord;
      setTeachers((currentTeachers) => [...currentTeachers, created].sort(compareTeachers));
      setTeacherName("");
      setTeacherId("");
      setTeacherPost("");
      setStatus(`Преподаватель ${created.name} добавлен.`);
    } catch {
      setStatus("Не удалось добавить преподавателя.");
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    if (!absenceTeacher) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && busy !== "absence") {
        setAbsenceTeacher(null);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [absenceTeacher, busy]);

  const openAbsenceDialog = (teacher: TeacherRecord) => {
    setAbsenceTeacher(teacher);
    setAbsenceDate(toLocalDateInput(new Date()));
    setAbsenceSlots(lessonSlots);
    setAbsenceReason("");
  };

  const toggleAbsenceSlot = (slot: number) => {
    setAbsenceSlots((currentSlots) => {
      if (currentSlots.includes(slot)) {
        return currentSlots.filter((currentSlot) => currentSlot !== slot);
      }
      return [...currentSlots, slot].sort((left, right) => left - right);
    });
  };

  const selectAllAbsenceSlots = () => {
    setAbsenceSlots(lessonSlots);
  };

  const createAbsence = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!absenceTeacher) {
      setStatus("Выберите преподавателя.");
      return;
    }
    const selectedSlots = [...absenceSlots].sort((left, right) => left - right);
    if (selectedSlots.length === 0) {
      setStatus("Выберите минимум одно занятие.");
      return;
    }

    setBusy("absence");
    try {
      const reason = absenceReason.trim();
      const absenceRequests =
        selectedSlots.length === lessonSlots.length
          ? [
              {
                date: absenceDate,
                all_day: true,
                time_slot_start: null,
                time_slot_end: null,
                reason,
              },
            ]
          : selectedSlots.map((slot) => ({
              date: absenceDate,
              all_day: false,
              time_slot_start: slot,
              time_slot_end: slot,
              reason,
            }));

      const createdAbsences = await Promise.all(
        absenceRequests.map(async (payload) => {
          const response = await fetch(`${apiBaseUrl}/teachers/${absenceTeacher.id}/absences`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...buildAuthHeaders(accessToken),
            },
            body: JSON.stringify(payload),
          });
          if (!response.ok) {
            throw new Error(await response.text());
          }
          return (await response.json()) as TeacherAbsenceRecord;
        }),
      );

      setTeachers((currentTeachers) =>
        currentTeachers.map((teacher) =>
          teacher.id === absenceTeacher.id
            ? {
                ...teacher,
                absences: [...createdAbsences, ...teacher.absences],
              }
            : teacher,
        ),
      );
      setAbsenceSlots(lessonSlots);
      setAbsenceReason("");
      setAbsenceTeacher(null);
      setStatus("Отсутствие преподавателя отмечено.");
    } catch {
      setStatus("Не удалось отметить отсутствие.");
    } finally {
      setBusy(null);
    }
  };

  const deleteAbsence = async (teacher: TeacherRecord, absence: TeacherAbsenceRecord) => {
    setBusy("absence");
    try {
      const response = await fetch(`${apiBaseUrl}/teachers/${teacher.id}/absences/${absence.id}`, {
        method: "DELETE",
        headers: buildAuthHeaders(accessToken),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      setTeachers((currentTeachers) =>
        currentTeachers.map((item) =>
          item.id === teacher.id
            ? { ...item, absences: item.absences.filter((currentAbsence) => currentAbsence.id !== absence.id) }
            : item,
        ),
      );
      setStatus("Отметка отсутствия удалена.");
    } catch {
      setStatus("Не удалось удалить отметку отсутствия.");
    } finally {
      setBusy(null);
    }
  };

  const deleteTeacher = async (teacher: TeacherRecord) => {
    const suffix = teacher.lesson_count > 0 ? ` ${teacher.lesson_count} занятий останутся без преподавателя.` : "";
    if (!window.confirm(`Удалить преподавателя ${teacher.name}?${suffix}`)) {
      return;
    }

    setBusy("delete");
    try {
      const response = await fetch(`${apiBaseUrl}/teachers/${teacher.id}`, {
        method: "DELETE",
        headers: buildAuthHeaders(accessToken),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      setTeachers((currentTeachers) => currentTeachers.filter((item) => item.id !== teacher.id));
      setAbsenceTeacher((currentTeacher) => (currentTeacher?.id === teacher.id ? null : currentTeacher));
      setStatus(`Преподаватель ${teacher.name} удалён.`);
    } catch {
      setStatus("Не удалось удалить преподавателя.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="teachers-page">
      <div className="import-head">
        <div>
          <h1>Преподаватели</h1>
        </div>
        <div className="import-chip-row">
          <div className="import-chip">{teachers.length} всего</div>
          <div className="import-chip">Занятия</div>
        </div>
      </div>

      <div className="teachers-grid">
        <div className="teachers-side">
          <form className="users-panel teachers-create" onSubmit={createTeacher}>
            <div className="users-panel__title">Новый преподаватель</div>
            <label className="field">
              <span>Имя</span>
              <input
                disabled={busy !== null}
                maxLength={200}
                onChange={(event) => setTeacherName(event.target.value)}
                placeholder="Иванова И.И."
                value={teacherName}
              />
            </label>
            <label className="field">
              <span>ID</span>
              <input
                disabled={busy !== null}
                maxLength={100}
                onChange={(event) => setTeacherId(event.target.value)}
                placeholder="необязательно"
                value={teacherId}
              />
            </label>
            <label className="field">
              <span>Должность</span>
              <input
                disabled={busy !== null}
                maxLength={200}
                onChange={(event) => setTeacherPost(event.target.value)}
                placeholder="преподаватель"
                value={teacherPost}
              />
            </label>
            <button className="import-button import-button--primary" disabled={busy !== null} type="submit">
              {busy === "create" ? "Добавляем..." : "Добавить"}
            </button>
            <div className="import-status">{status}</div>
          </form>
        </div>

        <div className="teachers-list">
          {busy === "load" ? (
            <div className="users-empty">Загрузка...</div>
          ) : teachers.length > 0 ? (
            <div className="rooms-card-list">
              {teachers.map((teacher) => (
                <div className="rooms-row" key={teacher.id}>
                  <div className="rooms-row__body">
                    <strong>{teacher.name}</strong>
                    <span>
                      {teacher.teacher_id}
                      {teacher.post ? ` · ${teacher.post}` : ""}
                    </span>
                    <span>{teacher.lesson_count} занятий</span>
                    {teacher.absences.length > 0 ? (
                      <div className="teachers-absence-list">
                        {teacher.absences.map((absence) => (
                          <div className="teachers-absence" key={absence.id}>
                            <span>{formatAbsence(absence)}</span>
                            <button
                              aria-label={`Удалить отсутствие ${teacher.name}`}
                              className="users-row__action"
                              disabled={busy !== null}
                              onClick={() => deleteAbsence(teacher, absence)}
                              type="button"
                            >
                              <Trash2 aria-hidden="true" size={14} strokeWidth={2} />
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="teachers-row-actions">
                    <button
                      className="users-row__action"
                      disabled={busy !== null}
                      onClick={() => openAbsenceDialog(teacher)}
                      type="button"
                    >
                      Отсутствует
                    </button>
                    <button
                      aria-label={`Удалить преподавателя ${teacher.name}`}
                      className="users-row__action rooms-row__delete"
                      disabled={busy !== null}
                      onClick={() => deleteTeacher(teacher)}
                      title="Удалить"
                      type="button"
                    >
                      <Trash2 aria-hidden="true" size={15} strokeWidth={2} />
                      <span>Удалить</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="users-empty">Преподавателей пока нет.</div>
          )}
        </div>
      </div>

      {absenceTeacher ? (
        <div className="teachers-modal" role="dialog" aria-modal="true" aria-labelledby="teacher-absence-title">
          <button
            aria-label="Закрыть меню отсутствия"
            className="teachers-modal__backdrop"
            disabled={busy === "absence"}
            onClick={() => setAbsenceTeacher(null)}
            type="button"
          />
          <form className="teachers-absence-dialog" onSubmit={createAbsence}>
            <div className="schedule-edit__section-head">
              <span>Отсутствие</span>
            </div>
            <div className="teachers-absence-dialog__title" id="teacher-absence-title">
              {absenceTeacher.name}
            </div>
            <label className="field">
              <span>Дата</span>
              <input
                disabled={busy !== null}
                onChange={(event) => setAbsenceDate(event.target.value)}
                type="date"
                value={absenceDate}
              />
            </label>
            <div className="teachers-slot-picker">
              <div className="teachers-slot-picker__head">
                <div className="teachers-slot-picker__label">Занятия</div>
                <button
                  className="teachers-select-all"
                  disabled={busy !== null || absenceSlots.length === lessonSlots.length}
                  onClick={selectAllAbsenceSlots}
                  type="button"
                >
                  Выбрать все
                </button>
              </div>
              <div className="teachers-slot-picker__buttons">
                {lessonSlots.map((slot) => {
                  const selected = absenceSlots.includes(slot);
                  return (
                    <button
                      aria-pressed={selected}
                      className={selected ? "teachers-slot-button teachers-slot-button--active" : "teachers-slot-button"}
                      disabled={busy !== null}
                      key={slot}
                      onClick={() => toggleAbsenceSlot(slot)}
                      type="button"
                    >
                      {slot}
                    </button>
                  );
                })}
              </div>
            </div>
            <label className="field">
              <span>Причина</span>
              <input
                disabled={busy !== null}
                maxLength={300}
                onChange={(event) => setAbsenceReason(event.target.value)}
                placeholder="необязательно"
                value={absenceReason}
              />
            </label>
            <div className="schedule-edit__actions">
              <button className="users-row__action" disabled={busy === "absence"} onClick={() => setAbsenceTeacher(null)} type="button">
                Отмена
              </button>
              <button className="import-button import-button--primary" disabled={busy !== null} type="submit">
                {busy === "absence" ? "Сохраняем..." : "Отметить"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}

function TimeProfilesPage({ accessToken }: { accessToken: string }) {
  const [activeTab, setActiveTab] = useState<"day" | "week">("day");
  const [dayProfiles, setDayProfiles] = useState<DayTimeProfile[]>([]);
  const [weekProfiles, setWeekProfiles] = useState<WeekTimeProfile[]>([]);
  const [editingDayProfile, setEditingDayProfile] = useState<DayTimeProfile | null>(null);
  const [editingWeekProfile, setEditingWeekProfile] = useState<WeekTimeProfile | null>(null);
  const [dayProfileName, setDayProfileName] = useState("");
  const [dayProfileSlots, setDayProfileSlots] = useState<DayTimeProfileSlot[]>(createDefaultDayTimeSlots());
  const [weekProfileName, setWeekProfileName] = useState("");
  const [weekProfileDays, setWeekProfileDays] = useState(createEmptyWeekProfileDays());
  const [status, setStatus] = useState("Загрузка профилей времени.");
  const [busy, setBusy] = useState<"load" | "day" | "week" | "delete" | null>(null);

  const loadProfiles = async () => {
    setBusy("load");
    try {
      const [dayResponse, weekResponse] = await Promise.all([
        fetch(`${apiBaseUrl}/time-profiles/day`, { headers: buildAuthHeaders(accessToken) }),
        fetch(`${apiBaseUrl}/time-profiles/week`, { headers: buildAuthHeaders(accessToken) }),
      ]);
      if (!dayResponse.ok || !weekResponse.ok) {
        throw new Error("failed to load time profiles");
      }
      const nextDayProfiles = (await dayResponse.json()) as DayTimeProfile[];
      const nextWeekProfiles = (await weekResponse.json()) as WeekTimeProfile[];
      setDayProfiles(nextDayProfiles);
      setWeekProfiles(nextWeekProfiles);
      setStatus(nextDayProfiles.length || nextWeekProfiles.length ? "Профили времени загружены." : "Профилей времени пока нет.");
    } catch {
      setStatus("Не удалось загрузить профили времени.");
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    void loadProfiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  const resetDayForm = () => {
    setEditingDayProfile(null);
    setDayProfileName("");
    setDayProfileSlots(createDefaultDayTimeSlots());
  };

  const resetWeekForm = () => {
    setEditingWeekProfile(null);
    setWeekProfileName("");
    setWeekProfileDays(createEmptyWeekProfileDays(dayProfiles[0]?.id ?? 0));
  };

  useEffect(() => {
    if (editingWeekProfile || weekProfileDays.some((day) => day.day_profile_id !== 0) || dayProfiles.length === 0) {
      return;
    }
    setWeekProfileDays(createEmptyWeekProfileDays(dayProfiles[0].id));
  }, [dayProfiles, editingWeekProfile, weekProfileDays]);

  const updateDaySlot = (slotNumber: number, field: "time_start" | "time_end", value: string) => {
    setDayProfileSlots((currentSlots) =>
      currentSlots.map((slot) => (slot.slot_number === slotNumber ? { ...slot, [field]: normalizeTimeInput(value) } : slot)),
    );
  };

  const saveDayProfile = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = dayProfileName.trim();
    if (!name) {
      setStatus("Введите название профиля дня.");
      return;
    }

    setBusy("day");
    try {
      const response = await fetch(
        editingDayProfile ? `${apiBaseUrl}/time-profiles/day/${editingDayProfile.id}` : `${apiBaseUrl}/time-profiles/day`,
        {
          method: editingDayProfile ? "PATCH" : "POST",
          headers: {
            "Content-Type": "application/json",
            ...buildAuthHeaders(accessToken),
          },
          body: JSON.stringify({ name, slots: dayProfileSlots }),
        },
      );
      if (response.status === 409) {
        setStatus("Профиль дня с таким названием уже есть.");
        return;
      }
      if (!response.ok) {
        throw new Error(await response.text());
      }
      resetDayForm();
      await loadProfiles();
      setStatus(editingDayProfile ? "Профиль дня обновлён." : "Профиль дня создан.");
    } catch {
      setStatus("Не удалось сохранить профиль дня.");
    } finally {
      setBusy(null);
    }
  };

  const editDayProfile = (profile: DayTimeProfile) => {
    setActiveTab("day");
    setEditingDayProfile(profile);
    setDayProfileName(profile.name);
    setDayProfileSlots(profile.slots.map((slot) => ({ ...slot })));
  };

  const deleteDayProfile = async (profile: DayTimeProfile) => {
    if (!window.confirm(`Удалить профиль дня ${profile.name}?`)) {
      return;
    }

    setBusy("delete");
    try {
      const response = await fetch(`${apiBaseUrl}/time-profiles/day/${profile.id}`, {
        method: "DELETE",
        headers: buildAuthHeaders(accessToken),
      });
      if (response.status === 409) {
        setStatus("Профиль дня используется в профиле недели.");
        return;
      }
      if (!response.ok) {
        throw new Error(await response.text());
      }
      if (editingDayProfile?.id === profile.id) {
        resetDayForm();
      }
      await loadProfiles();
      setStatus("Профиль дня удалён.");
    } catch {
      setStatus("Не удалось удалить профиль дня.");
    } finally {
      setBusy(null);
    }
  };

  const updateWeekDay = (weekday: number, dayProfileId: number) => {
    setWeekProfileDays((currentDays) =>
      currentDays.map((day) => (day.weekday === weekday ? { ...day, day_profile_id: dayProfileId } : day)),
    );
  };

  const saveWeekProfile = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = weekProfileName.trim();
    if (!name) {
      setStatus("Введите название профиля недели.");
      return;
    }
    if (dayProfiles.length === 0 || weekProfileDays.some((day) => day.day_profile_id === 0)) {
      setStatus("Выберите профиль дня для каждого дня недели.");
      return;
    }

    setBusy("week");
    try {
      const response = await fetch(
        editingWeekProfile ? `${apiBaseUrl}/time-profiles/week/${editingWeekProfile.id}` : `${apiBaseUrl}/time-profiles/week`,
        {
          method: editingWeekProfile ? "PATCH" : "POST",
          headers: {
            "Content-Type": "application/json",
            ...buildAuthHeaders(accessToken),
          },
          body: JSON.stringify({ name, days: weekProfileDays }),
        },
      );
      if (response.status === 409) {
        setStatus("Профиль недели с таким названием уже есть.");
        return;
      }
      if (!response.ok) {
        throw new Error(await response.text());
      }
      resetWeekForm();
      await loadProfiles();
      setStatus(editingWeekProfile ? "Профиль недели обновлён." : "Профиль недели создан.");
    } catch {
      setStatus("Не удалось сохранить профиль недели.");
    } finally {
      setBusy(null);
    }
  };

  const editWeekProfile = (profile: WeekTimeProfile) => {
    setActiveTab("week");
    setEditingWeekProfile(profile);
    setWeekProfileName(profile.name);
    setWeekProfileDays(profile.days.map((day) => ({ weekday: day.weekday, day_profile_id: day.day_profile_id })));
  };

  const deleteWeekProfile = async (profile: WeekTimeProfile) => {
    if (!window.confirm(`Удалить профиль недели ${profile.name}?`)) {
      return;
    }

    setBusy("delete");
    try {
      const response = await fetch(`${apiBaseUrl}/time-profiles/week/${profile.id}`, {
        method: "DELETE",
        headers: buildAuthHeaders(accessToken),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      if (editingWeekProfile?.id === profile.id) {
        resetWeekForm();
      }
      await loadProfiles();
      setStatus("Профиль недели удалён.");
    } catch {
      setStatus("Не удалось удалить профиль недели.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="time-profiles-page">
      <div className="import-head">
        <div>
          <h1>Профили времени</h1>
        </div>
        <div className="import-chip-row">
          <div className="import-chip">{dayProfiles.length} дневных</div>
          <div className="import-chip">{weekProfiles.length} недельных</div>
        </div>
      </div>

      <div className="time-profile-tabs" role="tablist" aria-label="Тип профиля времени">
        <button
          aria-pressed={activeTab === "day"}
          className={activeTab === "day" ? "time-profile-tab time-profile-tab--active" : "time-profile-tab"}
          onClick={() => setActiveTab("day")}
          type="button"
        >
          День
        </button>
        <button
          aria-pressed={activeTab === "week"}
          className={activeTab === "week" ? "time-profile-tab time-profile-tab--active" : "time-profile-tab"}
          onClick={() => setActiveTab("week")}
          type="button"
        >
          Неделя
        </button>
      </div>

      <div className="time-profiles-grid">
        {activeTab === "day" ? (
          <>
            <form className="users-panel time-profile-form" onSubmit={saveDayProfile}>
              <div className="users-panel__title">{editingDayProfile ? "Редактирование дня" : "Новый профиль дня"}</div>
              <label className="field">
                <span>Название</span>
                <input
                  disabled={busy !== null}
                  maxLength={150}
                  onChange={(event) => setDayProfileName(event.target.value)}
                  placeholder="Обычный день"
                  value={dayProfileName}
                />
              </label>
              <div className="time-slot-editor">
                {dayProfileSlots.map((slot) => (
                  <div className="time-slot-editor__row" key={slot.slot_number}>
                    <span>{slot.slot_number}</span>
                    <input
                      aria-label={`${slot.slot_number} занятие начало`}
                      disabled={busy !== null}
                      onChange={(event) => updateDaySlot(slot.slot_number, "time_start", event.target.value)}
                      type="time"
                      value={toTimeInput(slot.time_start)}
                    />
                    <input
                      aria-label={`${slot.slot_number} занятие конец`}
                      disabled={busy !== null}
                      onChange={(event) => updateDaySlot(slot.slot_number, "time_end", event.target.value)}
                      type="time"
                      value={toTimeInput(slot.time_end)}
                    />
                  </div>
                ))}
              </div>
              <div className="time-profile-actions">
                {editingDayProfile ? (
                  <button className="users-row__action" disabled={busy !== null} onClick={resetDayForm} type="button">
                    Отмена
                  </button>
                ) : null}
                <button className="import-button import-button--primary" disabled={busy !== null} type="submit">
                  {busy === "day" ? "Сохраняем..." : editingDayProfile ? "Сохранить" : "Создать"}
                </button>
              </div>
              <div className="import-status">{status}</div>
            </form>

            <div className="time-profile-list">
              {busy === "load" ? (
                <div className="users-empty">Загрузка...</div>
              ) : dayProfiles.length > 0 ? (
                <div className="rooms-card-list">
                  {dayProfiles.map((profile) => (
                    <div className="rooms-row time-profile-row" key={profile.id}>
                      <div className="rooms-row__body">
                        <strong>{profile.name}</strong>
                        <div className="time-profile-slots">
                          {profile.slots.map((slot) => (
                            <span key={slot.slot_number}>
                              {slot.slot_number}: {formatTimeShort(slot.time_start)}-{formatTimeShort(slot.time_end)}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="rooms-row-actions">
                        <button className="users-row__action" disabled={busy !== null} onClick={() => editDayProfile(profile)} type="button">
                          Изменить
                        </button>
                        <button className="users-row__action rooms-row__delete" disabled={busy !== null} onClick={() => deleteDayProfile(profile)} type="button">
                          <Trash2 aria-hidden="true" size={15} strokeWidth={2} />
                          <span>Удалить</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="users-empty">Профилей дня пока нет.</div>
              )}
            </div>
          </>
        ) : (
          <>
            <form className="users-panel time-profile-form" onSubmit={saveWeekProfile}>
              <div className="users-panel__title">{editingWeekProfile ? "Редактирование недели" : "Новый профиль недели"}</div>
              <label className="field">
                <span>Название</span>
                <input
                  disabled={busy !== null}
                  maxLength={150}
                  onChange={(event) => setWeekProfileName(event.target.value)}
                  placeholder="Учебная неделя"
                  value={weekProfileName}
                />
              </label>
              <div className="week-day-editor">
                {weekProfileDays.map((day) => (
                  <label className="field" key={day.weekday}>
                    <span>{weekdayLabels[day.weekday]}</span>
                    <select
                      disabled={busy !== null || dayProfiles.length === 0}
                      onChange={(event) => updateWeekDay(day.weekday, Number(event.target.value))}
                      value={day.day_profile_id}
                    >
                      <option value={0}>Выберите профиль</option>
                      {dayProfiles.map((profile) => (
                        <option key={profile.id} value={profile.id}>
                          {profile.name}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              <div className="time-profile-actions">
                {editingWeekProfile ? (
                  <button className="users-row__action" disabled={busy !== null} onClick={resetWeekForm} type="button">
                    Отмена
                  </button>
                ) : null}
                <button className="import-button import-button--primary" disabled={busy !== null || dayProfiles.length === 0} type="submit">
                  {busy === "week" ? "Сохраняем..." : editingWeekProfile ? "Сохранить" : "Создать"}
                </button>
              </div>
              <div className="import-status">{dayProfiles.length === 0 ? "Сначала создайте профиль дня." : status}</div>
            </form>

            <div className="time-profile-list">
              {busy === "load" ? (
                <div className="users-empty">Загрузка...</div>
              ) : weekProfiles.length > 0 ? (
                <div className="rooms-card-list">
                  {weekProfiles.map((profile) => (
                    <div className="rooms-row time-profile-row" key={profile.id}>
                      <div className="rooms-row__body">
                        <strong>{profile.name}</strong>
                        <div className="time-profile-week">
                          {profile.days.map((day) => (
                            <span key={day.weekday}>
                              {weekdayLabels[day.weekday]}: {day.day_profile_name}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="rooms-row-actions">
                        <button className="users-row__action" disabled={busy !== null} onClick={() => editWeekProfile(profile)} type="button">
                          Изменить
                        </button>
                        <button className="users-row__action rooms-row__delete" disabled={busy !== null} onClick={() => deleteWeekProfile(profile)} type="button">
                          <Trash2 aria-hidden="true" size={15} strokeWidth={2} />
                          <span>Удалить</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="users-empty">Профилей недели пока нет.</div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

type ImportApiResult = {
  timetable_count: number;
  group_count: number;
  lesson_count: number;
  empty_day_count: number;
};

function ImportPage({ accessToken }: { accessToken: string }) {
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
        headers: buildAuthHeaders(accessToken),
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

type ScheduleSlotRow = {
  room_name: string;
  building: string;
  room_is_excluded: boolean;
  room_exclusion_reason: string;
  lesson: LessonRecord | null;
};

type LessonRecord = {
  id: number;
  group_name: string;
  subject: string;
  teacher_name: string | null;
  teacher_is_absent: boolean;
  teacher_absence_reason: string;
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

type ScheduleEditorState =
  | {
      mode: "create";
      roomName: string;
      roomIsExcluded: boolean;
      roomExclusionReason: string;
    }
  | {
      mode: "update";
      lesson: LessonRecord;
      roomName: string;
      roomIsExcluded: boolean;
      roomExclusionReason: string;
    };

const lessonTimeSlots: Record<number, { start: string; end: string }> = {
  1: { start: "08:00:00", end: "09:30:00" },
  2: { start: "09:40:00", end: "11:10:00" },
  3: { start: "11:30:00", end: "13:00:00" },
  4: { start: "13:10:00", end: "14:40:00" },
  5: { start: "15:00:00", end: "16:30:00" },
  6: { start: "16:40:00", end: "18:10:00" },
  7: { start: "18:20:00", end: "19:50:00" },
};

function SchedulePage({ accessToken }: { accessToken: string }) {
  const today = useMemo(() => toLocalDateInput(new Date()), []);
  const [selectedDate, setSelectedDate] = useState(today);
  const [selectedSlot, setSelectedSlot] = useState(1);
  const [rows, setRows] = useState<ScheduleSlotRow[]>([]);
  const [availableTeachers, setAvailableTeachers] = useState<TeacherRecord[]>([]);
  const [editorState, setEditorState] = useState<ScheduleEditorState | null>(null);
  const [editGroupName, setEditGroupName] = useState("");
  const [editSubject, setEditSubject] = useState("");
  const [editTeacherName, setEditTeacherName] = useState("");
  const [editRoomName, setEditRoomName] = useState("");
  const [mutationWarnings, setMutationWarnings] = useState<ScheduleProblem[]>([]);
  const [mutationError, setMutationError] = useState("");
  const [status, setStatus] = useState("Выберите дату и номер занятия.");
  const [busy, setBusy] = useState(false);
  const [savingLesson, setSavingLesson] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const loadRows = async () => {
      setBusy(true);
      setEditorState(null);
      setMutationWarnings([]);
      setMutationError("");
      try {
        const response = await fetch(
          `${apiBaseUrl}/schedule/lessons?date=${encodeURIComponent(selectedDate)}&time_slot=${selectedSlot}`,
          {
            headers: buildAuthHeaders(accessToken),
          },
        );
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const payload = (await response.json()) as ScheduleSlotRow[];
        if (!cancelled) {
          setRows(payload);
          setStatus(payload.some((row) => row.lesson) ? "Расписание загружено." : "На выбранное занятие записей нет.");
        }
      } catch {
        if (!cancelled) {
          setRows([]);
          setStatus("Не удалось загрузить расписание.");
        }
      } finally {
        if (!cancelled) {
          setBusy(false);
        }
      }
    };

    void loadRows();
    return () => {
      cancelled = true;
    };
  }, [accessToken, selectedDate, selectedSlot, reloadToken]);

  useEffect(() => {
    let cancelled = false;
    const loadAvailableTeachers = async () => {
      try {
        const response = await fetch(
          `${apiBaseUrl}/teachers/available?date=${encodeURIComponent(selectedDate)}&time_slot=${selectedSlot}`,
          {
            headers: buildAuthHeaders(accessToken),
          },
        );
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const payload = (await response.json()) as TeacherRecord[];
        if (!cancelled) {
          setAvailableTeachers(payload);
        }
      } catch {
        if (!cancelled) {
          setAvailableTeachers([]);
        }
      }
    };

    void loadAvailableTeachers();
    return () => {
      cancelled = true;
    };
  }, [accessToken, selectedDate, selectedSlot]);

  const groupedRows = useMemo(() => groupScheduleRows(rows), [rows]);
  const availableRoomNames = useMemo(() => {
    return Array.from(new Set(rows.map((row) => row.room_name).filter((roomName) => roomName !== "Без кабинета"))).sort(compareRoomNames);
  }, [rows]);
  const selectedTeacher = useMemo(() => {
    const teacherName = editTeacherName.trim();
    if (!teacherName) {
      return null;
    }
    return availableTeachers.find((teacher) => teacher.name === teacherName) ?? null;
  }, [availableTeachers, editTeacherName]);

  useEffect(() => {
    if (!editorState) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !savingLesson) {
        setEditorState(null);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [editorState, savingLesson]);

  const openRowEditor = (row: ScheduleSlotRow) => {
    if (row.lesson) {
      setEditorState({
        mode: "update",
        lesson: row.lesson,
        roomName: row.room_name,
        roomIsExcluded: row.room_is_excluded,
        roomExclusionReason: row.room_exclusion_reason,
      });
      setEditGroupName(row.lesson.group_name);
      setEditSubject(row.lesson.subject);
      setEditTeacherName(row.lesson.teacher_name ?? "");
      setEditRoomName(editableScheduleRoomName(row.lesson.room_name ?? row.room_name));
      setMutationWarnings([]);
      return;
    }

    setEditorState({
      mode: "create",
      roomName: row.room_name,
      roomIsExcluded: row.room_is_excluded,
      roomExclusionReason: row.room_exclusion_reason,
    });
    setEditGroupName("");
    setEditSubject("");
    setEditTeacherName("");
    setEditRoomName(editableScheduleRoomName(row.room_name));
    setMutationWarnings([]);
  };

  const saveLesson = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editorState) {
      return;
    }
    if (!editGroupName.trim()) {
      setStatus("Введите группу.");
      return;
    }
    if (!editSubject.trim()) {
      setStatus("Введите предмет.");
      return;
    }
    if (editTeacherName.trim() && !selectedTeacher) {
      setStatus("Выберите доступного преподавателя.");
      return;
    }
    if (editRoomName.trim() && !availableRoomNames.includes(editRoomName.trim())) {
      setStatus("Выберите кабинет из списка.");
      return;
    }

    setSavingLesson(true);
    try {
      const response =
        editorState.mode === "update"
          ? await fetch(`${apiBaseUrl}/schedule/lessons/${editorState.lesson.id}`, {
              method: "PATCH",
              headers: {
                "Content-Type": "application/json",
                ...buildAuthHeaders(accessToken),
              },
              body: JSON.stringify({
                group_name: editGroupName.trim(),
                subject: editSubject.trim(),
                teacher_name: editTeacherName.trim(),
                teacher_id: selectedTeacher?.teacher_id ?? null,
                room_name: normalizeScheduleRoomName(editRoomName),
              }),
            })
          : await fetch(`${apiBaseUrl}/schedule/lessons`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                ...buildAuthHeaders(accessToken),
              },
              body: JSON.stringify(buildLessonCreatePayload({
                date: selectedDate,
                groupName: editGroupName.trim(),
                roomName: normalizeScheduleRoomName(editRoomName) ?? editorState.roomName,
                slot: selectedSlot,
                subject: editSubject.trim(),
                teacherName: editTeacherName.trim(),
                teacherId: selectedTeacher?.teacher_id ?? null,
                weekNumber: inferWeekNumber(rows, selectedDate),
              })),
            });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response));
      }
      const updated = (await response.json()) as LessonMutationResponse;
      setMutationError("");
      setEditorState({
        mode: "update",
        lesson: updated,
        roomName: updated.room_name ?? editorState.roomName,
        roomIsExcluded: editorState.roomIsExcluded,
        roomExclusionReason: editorState.roomExclusionReason,
      });
      setEditGroupName(updated.group_name);
      setEditSubject(updated.subject);
      setEditTeacherName(updated.teacher_name ?? "");
      setEditRoomName(editableScheduleRoomName(updated.room_name));
      setMutationWarnings(updated.warnings ?? []);
      setReloadToken((value) => value + 1);
      setStatus(
        updated.warnings && updated.warnings.length > 0
          ? "Сохранено с предупреждениями."
          : editorState.mode === "update"
            ? "Занятие обновлено."
            : "Занятие создано.",
      );
    } catch (error) {
      setMutationWarnings([]);
      setMutationError(error instanceof Error ? error.message : String(error));
      setStatus(editorState.mode === "update" ? "Не удалось сохранить занятие." : "Не удалось создать занятие.");
    } finally {
      setSavingLesson(false);
    }
  };

  const currentLesson = editorState?.mode === "update" ? editorState.lesson : null;
  const currentTeacherAbsenceReason = currentLesson?.teacher_is_absent
    ? currentLesson.teacher_absence_reason || "Причина не указана."
    : "";
  const currentRoomExclusionReason = editorState?.roomIsExcluded
    ? editorState.roomExclusionReason || "Причина не указана."
    : "";

  return (
    <div className="schedule-page">
      <div className="import-head">
        <div>
          <h1>Замены занятий</h1>
        </div>
        <div className="import-chip-row">
          <div className="import-chip">Дата</div>
          <div className="import-chip">№ занятия</div>
          <div className="import-chip">Кабинеты</div>
        </div>
      </div>

      <div className="schedule-sticky">
        <div className="schedule-toolbar">
          <label className="field">
            <span>Дата</span>
            <input
              onChange={(event) => setSelectedDate(event.target.value)}
              type="date"
              value={selectedDate}
            />
          </label>

          <div className="field">
            <span>№ занятия</span>
            <div className="lesson-switch" role="tablist" aria-label="Номер занятия">
              {Array.from({ length: 7 }, (_, index) => index + 1).map((slot) => (
                <button
                  aria-pressed={selectedSlot === slot}
                  className={selectedSlot === slot ? "lesson-switch__button lesson-switch__button--active" : "lesson-switch__button"}
                  key={slot}
                  onClick={() => setSelectedSlot(slot)}
                  type="button"
                >
                  {slot}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="schedule-status">{busy ? "Загружаем..." : status}</div>
      </div>

      {editorState ? (
        <div className="schedule-modal" role="dialog" aria-modal="true" aria-labelledby="schedule-edit-title">
          <button
            aria-label="Закрыть меню изменения"
            className="schedule-modal__backdrop"
            disabled={savingLesson}
            onClick={() => setEditorState(null)}
            type="button"
          />
          <form className="schedule-edit" onSubmit={saveLesson}>
            <div className="schedule-edit__title" id="schedule-edit-title">
              {editorState.roomName}
            </div>
            <section className="schedule-edit__section" aria-label="Текущие параметры">
              <div className="schedule-edit__section-head">
                <span>До</span>
              </div>
              <div className="schedule-edit__snapshot">
                <div className="schedule-edit__row">
                  <span>Группа</span>
                  <strong>{currentLesson?.group_name ?? "—"}</strong>
                </div>
                <div className="schedule-edit__row">
                  <span>Предмет</span>
                  <strong>{currentLesson?.subject ?? "Свободно"}</strong>
                </div>
                <div className="schedule-edit__row">
                  <span>Преподаватель</span>
                  <strong>{currentLesson?.teacher_name ?? "—"}</strong>
                </div>
                <div className="schedule-edit__row">
                  <span>Кабинет</span>
                  <strong>{currentLesson?.room_name ?? editorState.roomName}</strong>
                </div>
              </div>
            </section>
            {currentTeacherAbsenceReason || currentRoomExclusionReason ? (
              <section className="schedule-edit__lint" aria-label="Ограничения">
                <div className="schedule-edit__section-head">
                  <span>Ограничения</span>
                </div>
                {currentTeacherAbsenceReason ? (
                  <div className="schedule-edit__warning schedule-edit__warning--error">
                    <strong>Преподаватель отсутствует</strong>
                    <span>{currentTeacherAbsenceReason}</span>
                  </div>
                ) : null}
                {currentRoomExclusionReason ? (
                  <div className="schedule-edit__warning schedule-edit__warning--error">
                    <strong>Кабинет исключён</strong>
                    <span>{currentRoomExclusionReason}</span>
                  </div>
                ) : null}
              </section>
            ) : null}
            <section className="schedule-edit__section" aria-label="Новые параметры">
              <div className="schedule-edit__section-head">
                <span>После</span>
              </div>
              <div className="schedule-edit__fields">
                <label className="field">
                  <span>Кабинет</span>
                  <input
                    disabled={savingLesson}
                    list="available-rooms"
                    onChange={(event) => setEditRoomName(event.target.value)}
                    value={editRoomName}
                  />
                  <datalist id="available-rooms">
                    {availableRoomNames.map((roomName) => (
                      <option key={roomName} value={roomName} />
                    ))}
                  </datalist>
                </label>
                <label className="field">
                  <span>Группа</span>
                  <input disabled={savingLesson} onChange={(event) => setEditGroupName(event.target.value)} value={editGroupName} />
                </label>
                <label className="field">
                  <span>Предмет</span>
                  <input disabled={savingLesson} onChange={(event) => setEditSubject(event.target.value)} value={editSubject} />
                </label>
                <label className="field">
                  <span>Преподаватель</span>
                  <input
                    disabled={savingLesson}
                    list="available-teachers"
                    onChange={(event) => setEditTeacherName(event.target.value)}
                    value={editTeacherName}
                  />
                  <datalist id="available-teachers">
                    {availableTeachers.map((teacher) => (
                      <option key={teacher.id} value={teacher.name} />
                    ))}
                  </datalist>
                </label>
              </div>
            </section>
            {mutationError ? (
              <section className="schedule-edit__lint" aria-label="Ошибка сохранения" role="alert">
                <div className="schedule-edit__section-head">
                  <span>Ошибка · debug</span>
                </div>
                <div className="schedule-edit__error">{mutationError}</div>
              </section>
            ) : null}
            {mutationWarnings.length > 0 ? (
              <section className="schedule-edit__lint" aria-label="Предупреждения">
                <div className="schedule-edit__section-head">
                  <span>Предупреждения</span>
                </div>
                {mutationWarnings.map((warning, index) => (
                  <div className="schedule-edit__warning" key={`${warning.code}-${index}`}>
                    <strong>{warning.message}</strong>
                    <span>{formatProblemMeta(warning)}</span>
                  </div>
                ))}
              </section>
            ) : null}
            <div className="schedule-edit__actions">
              <button className="users-row__action" disabled={savingLesson} onClick={() => setEditorState(null)} type="button">
                Отмена
              </button>
              <button className="import-button import-button--primary" disabled={savingLesson} type="submit">
                {savingLesson ? "Сохраняем..." : editorState.mode === "create" ? "Создать" : "Сохранить"}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      <div className="schedule-table-wrap">
        {groupedRows.length > 0 ? (
          groupedRows.map((buildingGroup) => (
            <section className="schedule-building" key={buildingGroup.building}>
              <div className="schedule-building__head">
                <h2>{buildingGroup.building}</h2>
                <span>{buildingGroup.rooms.length} кабинетов</span>
              </div>
              <div className="schedule-table">
                <div className="schedule-table__head">
                  <div>Кабинет</div>
                  <div>Группа</div>
                  <div>Предмет</div>
                  <div>Преподаватель</div>
                  <div>Время</div>
                  <div>Статус</div>
                </div>
                {buildingGroup.rooms.map((row, index) => (
                  <button
                    className={
                      row.room_is_excluded || row.lesson?.teacher_is_absent
                        ? "schedule-table__row schedule-table__row--editable schedule-table__row--problem"
                        : "schedule-table__row schedule-table__row--editable"
                    }
                    disabled={savingLesson}
                    key={`${buildingGroup.building}-${row.room_name}-${row.lesson?.id ?? "empty"}-${index}`}
                    onClick={() => openRowEditor(row)}
                    type="button"
                  >
                    <div className="schedule-table__room">
                      <span>{row.room_name}</span>
                      {row.room_is_excluded ? (
                        <span className="schedule-reason-badge" title={row.room_exclusion_reason || "Причина не указана."}>
                          Кабинет: {formatScheduleReason(row.room_exclusion_reason)}
                        </span>
                      ) : null}
                    </div>
                    <div>{row.lesson ? row.lesson.group_name : "—"}</div>
                    <div>{row.lesson ? row.lesson.subject : "Свободно"}</div>
                    <div className="schedule-table__teacher">
                      <span>{row.lesson?.teacher_name ?? "—"}</span>
                      {row.lesson?.teacher_is_absent ? (
                        <span className="schedule-reason-badge" title={row.lesson.teacher_absence_reason || "Причина не указана."}>
                          Преподаватель: {formatScheduleReason(row.lesson.teacher_absence_reason)}
                        </span>
                      ) : null}
                    </div>
                    <div>{row.lesson ? `${formatTimeShort(row.lesson.time_start)} – ${formatTimeShort(row.lesson.time_end)}` : "—"}</div>
                    <div>
                      <span className={row.lesson ? "schedule-pill schedule-pill--busy" : "schedule-pill schedule-pill--free"}>
                        {row.lesson ? "Занято" : "Свободно"}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </section>
          ))
        ) : (
          <div className="users-empty">Нет кабинетов для выбранной даты и занятия.</div>
        )}
      </div>
    </div>
  );
}

function groupScheduleRows(rows: ScheduleSlotRow[]) {
  const groups = new Map<string, ScheduleSlotRow[]>();
  for (const row of rows) {
    const building = row.building || "Без корпуса";
    const list = groups.get(building) ?? [];
    list.push(row);
    groups.set(building, list);
  }

  return [...groups.entries()]
    .map(([building, rooms]) => ({
      building,
      rooms,
    }))
    .sort((left, right) => compareBuildings(left.building, right.building));
}

function groupRoomsByBuilding(rooms: RoomRecord[]) {
  const groups = new Map<string, RoomRecord[]>();
  for (const room of rooms) {
    const building = room.building || "Без корпуса";
    const list = groups.get(building) ?? [];
    list.push(room);
    groups.set(building, list);
  }

  return [...groups.entries()]
    .map(([building, roomList]) => ({
      building,
      rooms: roomList.sort(compareRooms),
    }))
    .sort((left, right) => compareBuildings(left.building, right.building));
}

function compareRooms(left: RoomRecord, right: RoomRecord) {
  return left.name.localeCompare(right.name, "ru", { numeric: true });
}

function compareGroups(left: GroupRecord, right: GroupRecord) {
  return left.name.localeCompare(right.name, "ru", { numeric: true });
}

function compareRoomNames(left: string, right: string) {
  return left.localeCompare(right, "ru", { numeric: true });
}

function compareTeachers(left: TeacherRecord, right: TeacherRecord) {
  return left.name.localeCompare(right.name, "ru", { numeric: true });
}

function toLocalDateInput(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function compareBuildings(left: string, right: string) {
  const leftRank = buildingRank(left);
  const rightRank = buildingRank(right);
  if (leftRank !== rightRank) {
    return leftRank - rightRank;
  }
  return left.localeCompare(right, "ru");
}

function buildingRank(building: string) {
  if (building === "Без корпуса") {
    return 999;
  }
  const match = building.match(/(\d+)/);
  if (match) {
    return Number(match[1]);
  }
  return 500;
}

function buildLessonCreatePayload({
  date,
  groupName,
  roomName,
  slot,
  subject,
  teacherId,
  teacherName,
  weekNumber,
}: {
  date: string;
  groupName: string;
  roomName: string;
  slot: number;
  subject: string;
  teacherId: string | null;
  teacherName: string;
  weekNumber: number;
}) {
  const lessonTime = lessonTimeSlots[slot] ?? lessonTimeSlots[1];
  return {
    group_name: groupName,
    course: 0,
    faculty: "",
    subject,
    teacher_name: teacherName || null,
    teacher_id: teacherId,
    teacher_post: "",
    room_name: roomName,
    date,
    time_start: lessonTime.start,
    time_end: lessonTime.end,
    weekday: getIsoWeekday(date),
    week_number: weekNumber,
    time_slot: slot,
    subgroup: 0,
    lesson_type: "",
  };
}

function inferWeekNumber(rows: ScheduleSlotRow[], selectedDate: string) {
  const lessonOnDate = rows.find((row) => row.lesson?.date === selectedDate)?.lesson;
  return lessonOnDate?.week_number ?? getIsoWeekNumber(selectedDate);
}

function getIsoWeekday(dateValue: string) {
  const day = new Date(`${dateValue}T00:00:00`).getDay();
  return day === 0 ? 7 : day;
}

function getIsoWeekNumber(dateValue: string) {
  const date = new Date(`${dateValue}T00:00:00`);
  const target = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNumber = target.getUTCDay() || 7;
  target.setUTCDate(target.getUTCDate() + 4 - dayNumber);
  const yearStart = new Date(Date.UTC(target.getUTCFullYear(), 0, 1));
  return Math.ceil(((target.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
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

function buildAuthHeaders(accessToken: string): HeadersInit {
  return {
    Authorization: `Bearer ${accessToken}`,
  };
}

// Debug passthrough: the API's raw `detail` string, shown as-is until the
// blocking rules settle down and each code gets its own Russian wording.
async function readErrorDetail(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") {
      return parsed.detail;
    }
    if (parsed.detail !== undefined) {
      return JSON.stringify(parsed.detail);
    }
  } catch {
    // Not JSON — fall through to the raw body.
  }
  return raw;
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  const datePart = formatDateParts(date.getFullYear(), date.getMonth() + 1, date.getDate());
  const timePart = `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
  return `${datePart} ${timePart}`;
}

function formatPlainDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) {
    return value;
  }
  return formatDateParts(year, month, day);
}

function formatDateParts(year: number, month: number, day: number) {
  return `${String(day).padStart(2, "0")}.${String(month).padStart(2, "0")}.${year}`;
}

function formatAbsence(absence: TeacherAbsenceRecord) {
  let scope = "весь день";
  if (!absence.all_day && absence.time_slot_start !== null && absence.time_slot_end !== null) {
    scope =
      absence.time_slot_start === absence.time_slot_end
        ? `${absence.time_slot_start} пара`
        : `${absence.time_slot_start}-${absence.time_slot_end} пары`;
  }
  return `${formatPlainDate(absence.date)} · ${scope}${absence.reason ? ` · ${absence.reason}` : ""}`;
}

function buildProblemFilterOptions(problems: ScheduleProblem[]) {
  const counts = new Map<string, number>();
  for (const problem of problems) {
    counts.set(problem.code, (counts.get(problem.code) ?? 0) + 1);
  }

  const knownOptions = defaultProblemFilterCodes.map((code) => ({
    code,
    count: counts.get(code) ?? 0,
    label: problemFilterLabels[code] ?? code,
  }));
  const unknownOptions = Array.from(counts.entries())
    .filter(([code]) => !defaultProblemFilterCodes.includes(code))
    .map(([code, count]) => ({
      code,
      count,
      label: problemFilterLabels[code] ?? code,
    }))
    .sort((left, right) => left.label.localeCompare(right.label, "ru"));

  return [
    {
      code: "all",
      count: problems.length,
      label: problemFilterLabels.all,
    },
    ...knownOptions,
    ...unknownOptions,
  ];
}

function formatProblemMeta(problem: ScheduleProblem) {
  const parts = [
    problem.date ? formatPlainDate(problem.date) : null,
    problem.week_number ? `${problem.week_number} неделя` : null,
    problem.time_slot ? `${problem.time_slot} пара` : null,
    problem.group_name,
    problem.teacher_name,
    problem.room_name,
  ].filter(Boolean);
  return parts.join(" · ");
}

function formatTimeShort(value: string) {
  return value.slice(0, 5);
}

function formatScheduleReason(value: string) {
  return value.trim() || "Причина не указана";
}

function editableScheduleRoomName(roomName: string | null) {
  return roomName && roomName !== "Без кабинета" ? roomName : "";
}

function normalizeScheduleRoomName(roomName: string) {
  const trimmed = roomName.trim();
  return trimmed ? trimmed : null;
}

const weekdayLabels: Record<number, string> = {
  1: "Пн",
  2: "Вт",
  3: "Ср",
  4: "Чт",
  5: "Пт",
  6: "Сб",
  7: "Вс",
};

function createDefaultDayTimeSlots(): DayTimeProfileSlot[] {
  return lessonSlots.map((slot) => {
    const timeSlot = lessonTimeSlots[slot] ?? lessonTimeSlots[1];
    return {
      slot_number: slot,
      time_start: timeSlot.start,
      time_end: timeSlot.end,
    };
  });
}

function createEmptyWeekProfileDays(dayProfileId = 0) {
  return lessonSlots.map((weekday) => ({
    weekday,
    day_profile_id: dayProfileId,
  }));
}

function toTimeInput(value: string) {
  return value.slice(0, 5);
}

function normalizeTimeInput(value: string) {
  return value.length === 5 ? `${value}:00` : value;
}
