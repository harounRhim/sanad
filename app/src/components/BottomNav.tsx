import { NavLink } from "react-router-dom";

const ITEMS = [
  { to: "/", label: "Journey", icon: "🗺", end: true },
  { to: "/surahs", label: "Read", icon: "📖", end: false },
  { to: "/search", label: "Search", icon: "🔍", end: false },
  { to: "/practice", label: "Practice", icon: "🎤", end: false },
  { to: "/due", label: "Review", icon: "🔁", end: false },
  { to: "/bookmarks", label: "Saved", icon: "🔖", end: false },
  { to: "/settings", label: "Settings", icon: "⚙", end: false },
];

export default function BottomNav() {
  return (
    <nav className="border-t border-brand-muted/15 bg-brand-surface dark:bg-brand-darkSurface">
      <div className="mx-auto flex max-w-3xl items-stretch justify-around">
        {ITEMS.map((it) => (
          <NavLink
            key={it.to}
            to={it.to}
            end={it.end}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium transition-colors ${
                isActive
                  ? "text-brand-emerald dark:text-brand-goldLight"
                  : "text-brand-muted dark:text-brand-darkMuted"
              }`
            }
          >
            <span className="text-lg leading-none">{it.icon}</span>
            {it.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
