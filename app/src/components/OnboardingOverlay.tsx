import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSurahs } from "../hooks/useQueries";
import { useActiveSlate } from "../hooks/useActiveSlate";
import { markOnboarded } from "../lib/onboarding";
import Spinner from "./Spinner";

// Gentle starting points: Al-Fātiḥa, the three Quls + other short, commonly
// memorized sūrahs, and a couple of beloved longer ones. Just suggestions —
// the search below reaches all 114.
const SUGGESTED = [1, 112, 113, 114, 103, 108, 110, 36, 67];

interface Props {
  name: string | null;
  onDone: () => void;
}

/** First-run guide, step 1: choose at least one sūrah to begin with. On
 * "Start" it claims a slate slot for each pick (so they show as active on the
 * Journey map) and lands the learner on the first one with ?welcome=1, where
 * SurahDetail's coach popup explains Recite-now vs Listen & Repeat. */
export default function OnboardingOverlay({ name, onDone }: Props) {
  const { data: surahs } = useSurahs();
  const slate = useActiveSlate();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<number[]>([]);

  const suggested = useMemo(
    () => SUGGESTED.map((n) => surahs?.find((s) => s.surah === n)).filter((s): s is NonNullable<typeof s> => Boolean(s)),
    [surahs]
  );

  const filtered = useMemo(() => {
    if (!surahs) return [];
    const q = query.trim().toLowerCase();
    if (!q) return surahs;
    return surahs.filter(
      (s) => s.name_tr.toLowerCase().includes(q) || String(s.surah) === q || s.name_ar.includes(query.trim())
    );
  }, [surahs, query]);

  const toggle = (n: number) =>
    setSelected((sel) => (sel.includes(n) ? sel.filter((x) => x !== n) : [...sel, n]));

  const finish = () => {
    markOnboarded();
    onDone();
  };

  const begin = () => {
    if (selected.length === 0) return;
    // Claim a slot for each pick (claimSlot is cap-limited and a no-op past
    // the cap) so they appear active on the map straight away.
    for (const n of selected) slate.claimSlot(n);
    finish();
    navigate(`/surah/${selected[0]}?welcome=1`);
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-brand-cream dark:bg-brand-dark">
      <div className="bg-brand-emerald px-5 pb-5 pt-10 text-white">
        <p className="quran text-2xl">سَنَد</p>
        <h1 className="mt-1 text-xl font-bold">Ahlan{name ? `, ${name}` : ""} 👋</h1>
        <p className="mt-1 text-sm text-white/85">
          Pick at least one sūrah to begin with — short ones are a gentle start,
          or search for any of the 114.
        </p>
      </div>

      {!surahs ? (
        <div className="flex-1"><Spinner label="Loading sūrahs…" /></div>
      ) : (
        <>
          {!query && (
            <div className="px-4 pt-3">
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-brand-muted dark:text-brand-darkMuted">
                Good places to start
              </p>
              <div className="flex flex-wrap gap-1.5">
                {suggested.map((s) => (
                  <button
                    key={s.surah}
                    onClick={() => toggle(s.surah)}
                    className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
                      selected.includes(s.surah)
                        ? "bg-brand-emerald text-white"
                        : "border border-brand-muted/25 text-brand-muted dark:text-brand-darkMuted"
                    }`}
                  >
                    {s.name_tr}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="px-4 pt-3">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search all sūrahs…"
              className="w-full rounded-xl border border-brand-muted/20 bg-brand-surface px-3 py-2.5 text-sm outline-none focus:border-brand-emerald dark:bg-brand-darkSurface"
            />
          </div>

          <div className="mt-2 flex-1 overflow-y-auto px-4">
            {filtered.map((s) => {
              const on = selected.includes(s.surah);
              return (
                <button
                  key={s.surah}
                  onClick={() => toggle(s.surah)}
                  className="flex w-full items-center gap-3 border-b border-brand-muted/10 py-3 text-left"
                >
                  <span
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md border-[1.5px] text-[11px] font-bold ${
                      on ? "border-brand-emerald bg-brand-emerald text-white" : "border-brand-muted/30 text-transparent"
                    }`}
                  >
                    ✓
                  </span>
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-muted/10 text-xs font-bold text-brand-muted dark:text-brand-darkMuted">
                    {s.surah}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">{s.name_tr}</span>
                    <span className="block text-xs text-brand-muted dark:text-brand-darkMuted">
                      {s.ayah_count} āyahs · {s.revelation_place === "makki" ? "Makki" : "Madani"}
                    </span>
                  </span>
                  <span className="quran shrink-0 text-lg text-brand-emerald dark:text-brand-goldLight">{s.name_ar}</span>
                </button>
              );
            })}
          </div>

          <div className="border-t border-brand-muted/15 bg-brand-surface p-4 dark:bg-brand-darkSurface">
            <button
              onClick={begin}
              disabled={selected.length === 0}
              className="w-full rounded-full bg-brand-emerald px-6 py-3.5 font-semibold text-white shadow-soft transition hover:bg-brand-emeraldDark disabled:opacity-40"
            >
              {selected.length
                ? `Start with ${selected.length} sūrah${selected.length > 1 ? "s" : ""} →`
                : "Choose a sūrah to continue"}
            </button>
            <button
              onClick={finish}
              className="mt-2 w-full text-center text-xs font-semibold text-brand-muted dark:text-brand-darkMuted"
            >
              Skip for now
            </button>
          </div>
        </>
      )}
    </div>
  );
}
