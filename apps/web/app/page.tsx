"use client";

import { useState } from "react";
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

const defaultSection = "Расписание";

export default function Home() {
  const [activeSection, setActiveSection] = useState(defaultSection);

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

      <section className="workspace" aria-label="Рабочая область">
        <div className="placeholder">
          <div className="placeholder__eyebrow">Раздел</div>
          <h1>{activeSection}</h1>
          <p>Раздел в разработке.</p>
        </div>
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
