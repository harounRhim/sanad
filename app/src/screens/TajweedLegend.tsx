import { TAJWEED_RULES, RULE_GROUPS } from "../lib/tajweed";

export default function TajweedLegend() {
  return (
    <div className="p-5">
      <h1 className="mb-1 text-xl font-bold">Tajweed Guide</h1>
      <p className="mb-5 text-sm text-brand-muted dark:text-brand-darkMuted">
        18 rules, color-coded as they appear in the reader.
      </p>

      {RULE_GROUPS.map((group) => (
        <section key={group} className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-brand-emerald dark:text-brand-goldLight">
            {group}
          </h2>
          <ul className="space-y-2">
            {TAJWEED_RULES.filter((r) => r.group === group).map((r) => (
              <li
                key={r.key}
                className="flex items-start gap-3 rounded-xl bg-brand-surface p-3.5 shadow-soft dark:bg-brand-darkSurface"
              >
                <span
                  className="mt-1 h-5 w-5 shrink-0 rounded-full"
                  style={{ backgroundColor: r.color }}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold">{r.en}</span>
                    <span className="quran text-lg">{r.ar}</span>
                  </div>
                  <p className="mt-0.5 text-sm text-brand-muted dark:text-brand-darkMuted">
                    {r.desc}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
