import { RECITERS } from "../lib/reciters";
import { useSettings } from "../state/SettingsContext";

export default function Reciters() {
  const { defaultReciter, set } = useSettings();

  return (
    <div className="p-5">
      <h1 className="mb-1 text-xl font-bold">Reciters</h1>
      <p className="mb-4 text-sm text-brand-muted dark:text-brand-darkMuted">
        {RECITERS.length} voices · tap to set your default.
      </p>

      <ul className="space-y-2">
        {RECITERS.map((r) => {
          const active = r.key === defaultReciter;
          return (
            <li key={r.key}>
              <button
                onClick={() => set("defaultReciter", r.key)}
                className={`flex w-full items-center justify-between rounded-xl p-3.5 text-left shadow-soft ${
                  active
                    ? "bg-brand-emerald text-white"
                    : "bg-brand-surface dark:bg-brand-darkSurface"
                }`}
              >
                <div>
                  <div className="font-semibold">{r.name}</div>
                  <div
                    className={`text-xs ${
                      active ? "text-white/70" : "text-brand-muted dark:text-brand-darkMuted"
                    }`}
                  >
                    {r.style}
                  </div>
                </div>
                {active && <span className="text-lg">✓</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
