import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useVersesByPairs } from "../hooks/useQueries";
import { useMemorization } from "../hooks/useMemorization";
import { useStreak } from "../hooks/useStreak";
import { useAutoRecorder } from "../hooks/useAutoRecorder";
import { blobToWav16kMono } from "../lib/wav";
import { gradeRecitation, isCorrectionConfigured, type GradeReport } from "../lib/correction";
import { ayahPassed, srsQuality } from "../lib/grading";
import { toArabicDigits } from "../lib/format";
import Spinner from "../components/Spinner";
import GradedAyah from "../components/GradedAyah";

type AyahStatus = "pass" | "needs_work";
const ADVANCE_DELAY_MS = 1400;

/** Roadmap V2 Phase 5 — spaced-repetition review. Recites whatever's due
 * today (SM-2 schedule from useMemorization/lib/srs.ts), one after another,
 * using the SAME continuous auto-recording flow as Practice/Drills. Each
 * grade both decides pass/fail (does the reciter move on) AND reschedules
 * the item's next review date via srsQuality() — no manual Again/Hard/Good/
 * Easy buttons needed, which is the whole payoff of building Phases 0/1/4
 * before this one. */
export default function Review() {
  const { entries, recordReview, loading: memLoading } = useMemorization();
  const streak = useStreak();
  const [sessionStart] = useState(() => Date.now());   // freeze "due" for this session

  const due = useMemo(
    () => entries.filter((e) => e.nextReviewAt <= sessionStart)
                 .sort((a, b) => a.nextReviewAt - b.nextReviewAt),
    [entries, sessionStart]
  );
  const pairs = useMemo(() => due.map((e) => ({ surah: e.surah, ayah: e.ayah })), [due]);
  const { data: versesUnordered } = useVersesByPairs(pairs);

  // Supabase's `.or()` doesn't promise result order — re-sort to match `due`
  // (most overdue first).
  const verses = useMemo(() => {
    if (!versesUnordered) return undefined;
    const byKey = new Map(versesUnordered.map((v) => [`${v.surah}:${v.ayah}`, v]));
    return due
      .map((e) => byKey.get(`${e.surah}:${e.ayah}`))
      .filter((v): v is NonNullable<typeof v> => Boolean(v));
  }, [versesUnordered, due]);

  const [idx, setIdx] = useState(0);
  const [grading, setGrading] = useState(false);
  const [report, setReport] = useState<GradeReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<Record<number, AyahStatus>>({});
  const [done, setDone] = useState(false);
  const advanceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const verse = verses?.[idx];

  useEffect(() => () => {
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
  }, []);

  const jumpTo = (i: number) => {
    if (!verses || i < 0 || i >= verses.length) return;
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
    setReport(null);
    setError(null);
    setDone(false);
    setIdx(i);
  };

  const advance = () => {
    if (!verses) return;
    if (idx + 1 < verses.length) {
      jumpTo(idx + 1);
    } else {
      setDone(true);
      autoRec.stop();
    }
  };

  const handleSegment = async (blob: Blob) => {
    if (!verse) return;
    setGrading(true);
    setError(null);
    try {
      const wav = await blobToWav16kMono(blob);
      const rep = await gradeRecitation(verse.surah, verse.ayah, wav);
      setReport(rep);
      const passed = ayahPassed(rep);
      setStatus((s) => ({ ...s, [idx]: passed ? "pass" : "needs_work" }));
      if (rep.content_status !== "content_mismatch") {
        recordReview(verse.surah, verse.ayah, srsQuality(rep));
        streak.recordActivity();
      }
      if (passed) advanceTimer.current = setTimeout(advance, ADVANCE_DELAY_MS);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Grading failed.");
    } finally {
      setGrading(false);
    }
  };

  const autoRec = useAutoRecorder(handleSegment);

  if (!isCorrectionConfigured) {
    return (
      <div className="p-6">
        <h1 className="text-xl font-bold">Review</h1>
        <div className="mt-4 rounded-xl bg-amber-500/15 p-4 text-sm text-amber-800 dark:text-amber-300">
          The correction service isn’t configured. Start the API
          (<code>server/run.ps1</code>) and set{" "}
          <code>VITE_CORRECTION_API_URL</code> in <code>app/.env.local</code>,
          then restart the dev server.
        </div>
      </div>
    );
  }

  return (
    <div className="p-5 pb-24">
      <h1 className="text-xl font-bold">Review</h1>
      <p className="mt-1 text-sm text-brand-muted">
        Spaced-repetition review of what you've memorized — due āyahs only.
      </p>

      {memLoading ? (
        // Entries are async (Supabase) — don't flash "🎉 Nothing due" at a
        // user whose due list simply hasn't arrived yet.
        <div className="mt-6"><Spinner label="Loading your schedule…" /></div>
      ) : due.length === 0 ? (
        <p className="mt-6 text-sm text-brand-muted">
          🎉 Nothing due right now — check back later, or{" "}
          <Link to="/practice" className="text-brand-emerald underline">
            recite more pages
          </Link>{" "}
          to build up your memorization.
        </p>
      ) : !verses ? (
        <div className="mt-6"><Spinner label="Loading due āyahs…" /></div>
      ) : done ? (
        <div className="mt-8 rounded-xl bg-brand-emerald/15 p-5 text-center">
          <p className="text-lg font-semibold">🎉 All caught up!</p>
          <p className="mt-1 text-sm text-brand-muted">
            You reviewed all {verses.length} due āyah{verses.length > 1 ? "s" : ""}.
          </p>
        </div>
      ) : (
        <>
          {/* Progress dots — tap to jump to that due āyah */}
          <div className="mt-4 flex flex-wrap gap-1.5">
            {verses.map((v, i) => {
              const st = status[i];
              const bg =
                i === idx ? "#0E5A4A" : st === "pass" ? "#2BB673" : st === "needs_work" ? "#E5392B" : "#D8D3C4";
              return (
                // 28px padded hit area around the 10px dot — see Practice.tsx.
                <button
                  key={`${v.surah}-${v.ayah}`}
                  onClick={() => jumpTo(i)}
                  title={`${v.surah}:${v.ayah}`}
                  aria-label={`Jump to ${v.surah}:${v.ayah}`}
                  className="-m-1.5 flex h-7 w-7 items-center justify-center"
                >
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: bg }} />
                </button>
              );
            })}
          </div>

          {/* The due ayah, colored by feedback once graded */}
          <div className="mt-4 rounded-2xl border border-brand-muted/15 p-5 text-center" dir="rtl">
            {report && report.content_status !== "content_mismatch" ? (
              <GradedAyah text={verse!.text} wordScores={report.word_scores} />
            ) : (
              <p className="quran text-3xl leading-loose">{verse!.text}</p>
            )}
            <div className="mt-2 text-xs text-brand-muted" dir="ltr">
              {verse!.surah}:{verse!.ayah} · {toArabicDigits(verse!.ayah)} · {idx + 1} of{" "}
              {verses.length} due
            </div>
          </div>

          {/* Continuous listening controls */}
          <div className="mt-6 flex flex-col items-center gap-3">
            {!autoRec.listening ? (
              <button
                onClick={autoRec.start}
                className="rounded-full bg-brand-emerald px-8 py-4 font-semibold text-white shadow-soft"
              >
                🎙 Start review
              </button>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <button
                  onClick={autoRec.stop}
                  className="flex items-center gap-2 rounded-full bg-brand-red px-8 py-4 text-white shadow-soft"
                >
                  <span className="h-3 w-3 animate-pulse rounded-full bg-white" />
                  Stop
                </button>
                <div className="h-1.5 w-40 overflow-hidden rounded-full bg-brand-muted/20">
                  <div
                    className="h-full bg-brand-emerald transition-[width]"
                    style={{ width: `${Math.min(100, autoRec.volume * 400)}%` }}
                  />
                </div>
                <p className="text-xs text-brand-muted">
                  {grading ? "Checking…" : "Listening — recite this āyah from memory."}
                </p>
              </div>
            )}
            {report && !grading && ayahPassed(report) && (
              <p className="text-sm text-brand-emerald">✅ Correct — next review scheduled.</p>
            )}
            {report && !grading && !ayahPassed(report) && report.content_status !== "content_mismatch" && (
              <p className="text-sm text-brand-red">
                🔁 Not quite — try this one again, still listening.
              </p>
            )}
            {autoRec.error && <p className="text-sm text-brand-red">{autoRec.error}</p>}
            {error && <p className="text-sm text-brand-red">{error}</p>}
          </div>

          {report?.content_status === "content_mismatch" && (
            <div className="mt-6 rounded-xl bg-amber-500/15 p-4 text-sm text-amber-800 dark:text-amber-300">
              <p className="font-semibold">This doesn’t sound like this āyah.</p>
              {report.decoded_text && (
                <p className="mt-2 text-xs opacity-80" dir="rtl">We heard: {report.decoded_text}</p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
