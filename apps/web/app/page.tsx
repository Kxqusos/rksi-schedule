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
  { label: "Расписание", icon: CalendarDays, active: true },
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

export default function Home() {
  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Основная навигация">
        <div className="sidebar__brand">
          <div className="sidebar__mark" aria-hidden="true">
            R
          </div>
          <div>
            <div className="sidebar__title">RKSI Schedule</div>
            <div className="sidebar__caption">Оператор</div>
          </div>
        </div>

        <nav className="sidebar__nav">
          <NavGroup title="Основное" items={primaryNav} />
          <NavGroup title="Операции" items={operationsNav} />
          <NavGroup title="Администрирование" items={adminNav} />
        </nav>
      </aside>

      <section className="workspace" aria-label="Рабочая область" />
    </main>
  );
}

type NavItem = {
  label: string;
  icon: LucideIcon;
  active?: boolean;
};

function NavGroup({ title, items }: { title: string; items: NavItem[] }) {
  return (
    <div className="nav-group">
      <div className="nav-group__title">{title}</div>
      <div className="nav-group__items">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <button
              className={item.active ? "nav-item nav-item--active" : "nav-item"}
              key={item.label}
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
