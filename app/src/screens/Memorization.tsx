import { Link } from "react-router-dom";
import { useSurahs } from "../hooks/useQueries";
import { useMemorization } from "../hooks/useMemorization";
import type { MemorizationStatus } from "../lib/types";
import Spinner from "../components/Spinner";

const STATUS_COLOR: Record<MemorizationStatus, string> = {
  mastered: "#2BB673",
  reviewing: "#C9A227",
  learning: "#E8A33D",
};

/** Roadmap V2 Phase 4 — memorization (hifz) tracker overview. Purely a
 * read-out of app/src/hooks/useMemorization.ts, fed automatically by
 * Practice.tsx's grading results; nothing here is graded or ML-driven. */
export default function Memorization() {
  const { data: surahs } = useSurahs();
  const { entries, loading } = useMemorization();

  // Entries are async (Supabase) — don't flash "No recitations tracked yet"
  // at a user whose progress simply hasn't arrived.
  if (loading) {
    return <div className="p-6"><Spinner label="Loading your progress…" /></div>;
  }

  const bySurah = new Map<number, Record<MemorizationStatus, number>>();
  for (const e of entries) {
    const cur = bySurah.get(e.surah) ?? { learning: 0, reviewing: 0, mastered: 0 };
    cur[e.status] += 1;
    bySurah.set(e.surah, cur);
  }
  const totalMastered = entries.filter((e) => e.status === "mastered").length;
  const dueCount = entries.filter((e) => e.nextReviewAt <= Date.now()).length;

  return (
    <div className="p-5 pb-24">
      <h1 className="text-xl font-bold">Memorization progress</h1>
      {dueCount > 0 && (
        <Link
          to="/review"
          className="mt-2 block rounded-xl bg-brand-gold/15 p-3 text-sm font-medium text-brand-ink dark:text-brand-darkInk"
        >
          🔁 {dueCount} āyah{dueCount === 1 ? "" : "s"} due for review →
        </Link>
      )}
      <p className="mt-2 text-sm text-brand-muted">
        Tracked automatically as you recite in{" "}
        <Link to="/practice" className="text-brand-emerald underline">Practice</Link> —{" "}
        {totalMastered} āyah{totalMastered === 1 ? "" : "s"} mastered so far.
      </p>

      <div className="mt-6 space-y-3">
        {surahs
          ?.filter((s) => bySurah.has(s.surah))
          .map((s) => {
            const counts = bySurah.get(s.surah)!;
            const tracked = counts.learning + counts.reviewing + counts.mastered;
            const untouched = s.ayah_count - tracked;
            return (
              <div key={s.surah} className="rounded-xl border border-brand-muted/15 p-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{s.surah}. {s.name_tr}</span>
                  <span className="quran text-base">{s.name_ar}</span>
                </div>
                <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-brand-muted/15">
                  {(["mastered", "reviewing", "learning"] as const).map((st) => (
                    <div
                      key={st}
                      style={{
                        width: `${(counts[st] / s.ayah_count) * 100}%`,
                        backgroundColor: STATUS_COLOR[st],
                      }}
                    />
                  ))}
                </div>
                <div className="mt-1 text-xs text-brand-muted">
                  {counts.mastered} mastered · {counts.reviewing} reviewing ·{" "}
                  {counts.learning} learning
                  {untouched > 0 ? ` · ${untouched} not yet attempted` : ""}
                </div>
              </div>
            );
          })}

        {bySurah.size === 0 && (
          <p className="text-sm text-brand-muted">
            No recitations tracked yet —{" "}
            <Link to="/practice" className="text-brand-emerald underline">
              head to Practice
            </Link>{" "}
            and recite a page to start building your progress.
          </p>
        )}
      </div>
    </div>
  );
}
