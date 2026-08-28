import { Link } from "react-router-dom";
import { useSurahs } from "../hooks/useQueries";
import { useMemorization } from "../hooks/useMemorization";
import type { MemorizationEntry } from "../lib/types";
import Spinner from "../components/Spinner";

type Urgency = "urgent" | "due" | "routine";

const URGENCY_LABEL: Record<Urgency, string> = { urgent: "Weak", due: "Due", routine: "Routine" };
const URGENCY_COLOR: Record<Urgency, string> = { urgent: "#E5392B", due: "#E8A33D", routine: "#2BB673" };

/** A just-reset streak (last attempt failed) reads as the most urgent case;
 * a healthy status (several consecutive passes) reads as routine upkeep
 * rather than something to worry about — same signal Memorization.tsx
 * already displays, just used here to triage instead of summarize. */
function urgencyFor(e: MemorizationEntry): Urgency {
  if (e.streak === 0) return "urgent";
  if (e.status === "mastered" || e.status === "reviewing") return "routine";
  return "due";
}

const RANK: Record<Urgency, number> = { urgent: 0, due: 1, routine: 2 };

/** Interface spec §04.6 — Due for Rework. Groups the existing SM-2 due list
 * (same filter Review.tsx already uses) by sūrah so it reads as a triaged
 * list instead of a flat queue. Tapping through still uses the real,
 * existing Review.tsx flow — this screen only adds the "what needs rework"
 * overview it never had a home for. */
export default function DueForRework() {
  const { data: surahs } = useSurahs();
  const { entries, loading } = useMemorization();

  // Entries are async (Supabase) — rendering before they arrive would flash
  // the "🎉 Nothing due" empty state at every user who actually has work due.
  if (loading) {
    return <div className="p-6"><Spinner label="Loading your schedule…" /></div>;
  }

  const due = entries.filter((e) => e.nextReviewAt <= Date.now());

  const bySurah = new Map<number, MemorizationEntry[]>();
  for (const e of due) {
    (bySurah.get(e.surah) ?? bySurah.set(e.surah, []).get(e.surah)!).push(e);
  }

  const rows = Array.from(bySurah.entries())
    .map(([surah, list]) => {
      const urgency = list.reduce<Urgency>(
        (worst, e) => (RANK[urgencyFor(e)] < RANK[worst] ? urgencyFor(e) : worst),
        "routine"
      );
      const ayahs = list.map((e) => e.ayah).sort((a, b) => a - b);
      return { surah, list, urgency, ayahs };
    })
    .sort((a, b) => RANK[a.urgency] - RANK[b.urgency] || a.surah - b.surah);

  return (
    <div className="p-5 pb-24">
      <Link to="/" className="text-sm text-brand-muted dark:text-brand-darkMuted">← Journey</Link>
      <h1 className="mt-2 text-xl font-bold">Due for rework</h1>
      <p className="mt-1 text-sm text-brand-muted dark:text-brand-darkMuted">
        From your spaced-repetition schedule — sorted by what's actually weak, not just what's due.
      </p>

      <div className="mt-4 flex items-center justify-between rounded-xl bg-brand-gold/15 p-3">
        <div>
          <p className="text-2xl font-bold tabular-nums">{due.length}</p>
          <p className="text-xs text-brand-muted dark:text-brand-darkMuted">Due today</p>
        </div>
        {due.length > 0 && (
          <Link
            to="/review"
            className="rounded-full bg-brand-emerald px-5 py-2.5 text-sm font-semibold text-white shadow-soft"
          >
            Review all
          </Link>
        )}
      </div>

      <div className="mt-4 space-y-2">
        {rows.map(({ surah, ayahs, urgency }) => {
          const s = surahs?.find((x) => x.surah === surah);
          return (
            <Link
              key={surah}
              to="/review"
              className="flex items-center gap-3 rounded-xl border border-brand-muted/15 p-3"
            >
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: URGENCY_COLOR[urgency] }}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{s?.name_tr ?? `Sūrah ${surah}`}</p>
                <p className="truncate text-xs text-brand-muted dark:text-brand-darkMuted">
                  {ayahs.length === 1 ? `Āyah ${ayahs[0]}` : `${ayahs.length} āyahs due`}
                </p>
              </div>
              <span className="shrink-0 text-xs font-bold" style={{ color: URGENCY_COLOR[urgency] }}>
                {URGENCY_LABEL[urgency]}
              </span>
            </Link>
          );
        })}

        {due.length === 0 && (
          <p className="mt-6 text-center text-sm text-brand-muted dark:text-brand-darkMuted">
            🎉 Nothing due right now — check back later.
          </p>
        )}
      </div>
    </div>
  );
}
