import { useState } from "react";
import { useNavigate, useParams, useSearchParams, Link } from "react-router-dom";
import { useSurahs, useVerses, usePages } from "../hooks/useQueries";
import { useMemorization } from "../hooks/useMemorization";
import { useActiveSlate } from "../hooks/useActiveSlate";
import { memorizedRatio, pagesForSurah, surahTier } from "../lib/tiers";
import type { MemorizationStatus } from "../lib/types";
import Spinner from "../components/Spinner";

const DOT_COLOR: Record<MemorizationStatus, string> = {
  mastered: "#2BB673",
  reviewing: "#C9A227",
  learning: "#E8A33D",
};
const DOT_UNTOUCHED = "#D8D3C4";

function daysUntil(ts: number): string {
  const days = Math.ceil((ts - Date.now()) / 86_400_000);
  if (days <= 0) return "due now";
  if (days === 1) return "1d";
  return `${days}d`;
}

/** Interface spec §04.2 — Sūrah Detail. What a Journey Map node opens into:
 * memorization ring (reuses the existing mastered-ratio signal, see
 * lib/tiers.ts), itinerary CTAs, ayah dot row, and the §06 step-back action.
 * "Recite now" is the real, working Practice.tsx flow (§04.4) — this screen
 * adds no new grading, only a richer entry point into it. */
export default function SurahDetail() {
  const { id } = useParams();
  const surah = Number(id);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  // Coach popup from the first-run guide (OnboardingOverlay lands here with
  // ?welcome=1). Explains the two ways in before the learner picks.
  const [showCoach, setShowCoach] = useState(params.get("welcome") === "1");

  const { data: surahs } = useSurahs();
  const { data: verses } = useVerses(surah);
  const { data: pages } = usePages();
  const { entries: allEntries, loading: memLoading } = useMemorization();
  const slate = useActiveSlate();

  const info = surahs?.find((s) => s.surah === surah);
  const entries = allEntries.filter((e) => e.surah === surah);

  // memLoading included so the ring/dots don't flash 0%/untouched before the
  // (async, Supabase-backed) progress arrives.
  if (!info || !verses || !pages || memLoading) {
    return (
      <div className="p-6">
        <Spinner label="Loading sūrah…" />
      </div>
    );
  }

  const tier = surahTier(surah, info.ayah_count, allEntries);
  const isActive = slate.isActive(surah);
  const ratio = memorizedRatio(surah, info.ayah_count, allEntries);
  const pct = Math.round(ratio * 100);
  const pageCount = pagesForSurah(surah, info.ayah_count, pages);

  const dueCount = entries.filter((e) => e.nextReviewAt <= Date.now()).length;
  const nextReview = entries
    .map((e) => e.nextReviewAt)
    .filter((t) => t > Date.now())
    .sort((a, b) => a - b)[0];

  /** §08 Q8's simplest resolution for a first build: tapping "Recite now"
   * on a not-yet-active sūrah is the genuine attempt that claims a slot —
   * blocked up front (before Practice even opens) if the slate is full,
   * rather than silently letting the recitation happen and then failing to
   * register it. A real "did they actually recite anything" check (only
   * claim after real accuracy comes back) is a follow-up refinement. */
  const goRecite = () => {
    if (!isActive && !slate.claimSlot(surah)) return;
    navigate(`/practice?surah=${surah}`);
  };

  const stepBack = () => {
    if (!window.confirm(`Step back from ${info.name_tr}? Your progress is kept, but this frees the slot only after a 72-hour cooldown.`)) {
      return;
    }
    slate.stepBack(surah);
  };

  return (
    <div className="pb-24">
      {showCoach && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 backdrop-blur-sm sm:items-center">
          <div className="w-full max-w-sm rounded-3xl bg-brand-cream p-6 shadow-soft dark:bg-brand-darkSurface">
            <p className="text-center text-3xl">🧭</p>
            <h2 className="mt-2 text-center text-lg font-bold">Here's {info.name_tr}</h2>
            <p className="mt-1 text-center text-sm text-brand-muted dark:text-brand-darkMuted">
              Two ways to work on it — pick whichever fits you:
            </p>
            <div className="mt-4 space-y-3">
              <div className="rounded-2xl border border-brand-muted/15 p-3">
                <p className="text-sm font-semibold text-brand-emerald dark:text-brand-goldLight">🎧 Listen &amp; Repeat</p>
                <p className="mt-0.5 text-xs text-brand-muted dark:text-brand-darkMuted">
                  New to this sūrah? Learn it āyah by āyah — and you choose which
                  āyah to start or continue from.
                </p>
              </div>
              <div className="rounded-2xl border border-brand-muted/15 p-3">
                <p className="text-sm font-semibold text-brand-emerald dark:text-brand-goldLight">🎙 Recite now</p>
                <p className="mt-0.5 text-xs text-brand-muted dark:text-brand-darkMuted">
                  Already memorized some of it? Recite from memory and get
                  instant word-by-word correction.
                </p>
              </div>
            </div>
            <button
              onClick={() => setShowCoach(false)}
              className="mt-5 w-full rounded-full bg-brand-emerald px-6 py-3 font-semibold text-white shadow-soft"
            >
              Got it
            </button>
          </div>
        </div>
      )}

      <header className="bg-brand-emerald px-5 pb-6 pt-8 text-white">
        <Link to="/" className="text-sm text-white/70">← Journey</Link>
        <p className="mt-2 text-xs uppercase tracking-wide text-white/70">
          Sūrah {info.surah} · {info.revelation_place === "makki" ? "Makki" : "Madani"}
        </p>
        <div className="mt-1 flex items-baseline justify-between">
          <h1 className="text-2xl font-bold">{info.name_tr}</h1>
          <span className="quran text-3xl">{info.name_ar}</span>
        </div>
        <p className="mt-1 text-sm text-white/80">
          {info.ayah_count} āyahs · {pageCount} page{pageCount === 1 ? "" : "s"}
        </p>
      </header>

      <div className="p-5">
        {/* Memorization ring */}
        <div className="flex items-center gap-4 rounded-2xl border border-brand-muted/15 bg-brand-surface p-4 shadow-soft dark:bg-brand-darkSurface">
          <div
            className="flex h-[74px] w-[74px] shrink-0 items-center justify-center rounded-full"
            style={{ background: `conic-gradient(#0E5A4A 0 ${pct}%, #DDD5C3 ${pct}% 100%)` }}
          >
            <div className="flex h-[58px] w-[58px] items-center justify-center rounded-full bg-brand-cream text-[15px] font-extrabold tabular-nums dark:bg-brand-dark">
              {pct}%
            </div>
          </div>
          <div>
            <p className="text-sm font-semibold">Memorized so far</p>
            <p className="mt-0.5 text-xs text-brand-muted dark:text-brand-darkMuted">
              Based on your tracked recitations, āyah by āyah.
            </p>
          </div>
        </div>

        {/* Ayah dot row */}
        <div className="mt-4 flex flex-wrap gap-1.5">
          {verses.map((v) => {
            const e = entries.find((x) => x.ayah === v.ayah);
            const bg = e ? DOT_COLOR[e.status] : DOT_UNTOUCHED;
            return (
              <span
                key={v.ayah}
                title={`${surah}:${v.ayah}${e ? ` — ${e.status}` : ""}`}
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: bg }}
              />
            );
          })}
        </div>

        {/* Stats */}
        <div className="mt-4 flex gap-3 text-center text-sm">
          <div className="flex-1 rounded-xl border border-brand-muted/15 p-3">
            <p className="text-lg font-bold tabular-nums">{dueCount}</p>
            <p className="text-xs text-brand-muted dark:text-brand-darkMuted">Due for rework</p>
          </div>
          <div className="flex-1 rounded-xl border border-brand-muted/15 p-3">
            <p className="text-lg font-bold tabular-nums">{nextReview ? daysUntil(nextReview) : "—"}</p>
            <p className="text-xs text-brand-muted dark:text-brand-darkMuted">Next review</p>
          </div>
        </div>

        {/* CTAs */}
        <div className="mt-5 space-y-2">
          <Link
            to={`/listen/${surah}`}
            className="block w-full rounded-full bg-brand-emerald/10 px-6 py-3.5 text-center font-semibold text-brand-emerald dark:text-brand-goldLight"
          >
            🎧 Listen &amp; Repeat
          </Link>
          <button
            onClick={goRecite}
            className="block w-full rounded-full bg-brand-emerald px-6 py-3.5 text-center font-semibold text-white shadow-soft"
          >
            🎙 Recite now
          </button>
          {!isActive && slate.slotsOpen <= 0 && (
            <p className="text-center text-xs text-brand-red">
              Your active slate is full — step back from another sūrah or finish one first (§06).
            </p>
          )}
        </div>

        {isActive && tier !== "retained" && (
          <div className="mt-4">
            <button
              onClick={stepBack}
              className="flex w-full items-center justify-center gap-2 rounded-full border border-brand-muted/30 px-6 py-3 text-sm font-semibold text-brand-muted transition-colors hover:border-brand-red/40 hover:bg-brand-red/5 hover:text-brand-red dark:text-brand-darkMuted"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                className="h-4 w-4"
                aria-hidden
              >
                <path d="M9 14 4 9l5-5" />
                <path d="M4 9h11a5 5 0 0 1 5 5v2" />
              </svg>
              Step back from this sūrah
            </button>
            <p className="mt-1.5 text-center text-[11px] text-brand-muted dark:text-brand-darkMuted">
              Frees a slate slot — your progress is kept, and you can return after a 72-hour cooldown.
            </p>
          </div>
        )}

        <div className="mt-6 flex justify-center gap-4 text-xs text-brand-muted dark:text-brand-darkMuted">
          <Link to="/due" className="underline">Due for rework →</Link>
          <Link to={`/read/${surah}`} className="underline">Read this sūrah →</Link>
        </div>
      </div>
    </div>
  );
}
