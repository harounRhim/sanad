import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useSurahs, useVerses, useAudio } from "../hooks/useQueries";
import { useAutoRecorder } from "../hooks/useAutoRecorder";
import { useMemorization } from "../hooks/useMemorization";
import { useStreak } from "../hooks/useStreak";
import { useActiveSlate } from "../hooks/useActiveSlate";
import { usePlayer } from "../state/PlayerContext";
import { useSettings } from "../state/SettingsContext";
import { blobToWav16kMono } from "../lib/wav";
import { gradeClip, isCorrectionConfigured, type AyahTaggedWordScore, type ClipReport } from "../lib/correction";
import { memorizedRatio } from "../lib/tiers";
import Spinner from "../components/Spinner";
import GradedSurah from "../components/GradedSurah";
import SessionSummary from "../components/SessionSummary";

type Stage = "listen" | "echo" | "recall" | "blind";
const STAGES: Stage[] = ["listen", "echo", "recall", "blind"];
const STAGE_LABEL: Record<Stage, string> = {
  listen: "🎧 Listen",
  echo: "🔁 Echo",
  recall: "📖 Recall",
  blind: "🙈 Blind",
};
const BLIND_STREAK_TARGET = 2; // §05 Tier 2: clean Blind pass, twice in a row
const FALLBACK_AFTER_FAILS = 3; // real difficulty -> drop back to Recall for support
const ADVANCE_DELAY_MS = 1100;
// Same threshold Practice.tsx uses (see PASS_RATIO there) — validated
// against real audio. An earlier version of `clean()` here required EVERY
// word to come back content_ok, which is stricter than the ASR's real noise
// floor supports: a handful of individual words routinely misfire even on a
// genuinely correct recitation, so that bar produced false "Not quite"s on
// correct recitations. Recall/Blind still care about CONTENT correctness
// specifically (content_ok, not the tajweed-inclusive `verdict` Practice
// uses) — just not literally 100% of words.
const PASS_RATIO = 0.5;

const CHUNK_SIZES = [1, 2, 3] as const;
const CHUNK_SIZE_KEY = "sanad.listenRepeat.chunkSize";

function loadChunkSize(): number {
  try {
    const n = Number(localStorage.getItem(CHUNK_SIZE_KEY));
    return (CHUNK_SIZES as readonly number[]).includes(n) ? n : 1;
  } catch {
    return 1;
  }
}

/** A chunk's clip "passes" a stage: content recognized in this sūrah, the
 * clip covers essentially the whole chunk (tolerant of 1 missing word, same
 * as Practice.tsx), and at least PASS_RATIO of the covered words are
 * content_ok. Checks words tagged to ANY āyah in [chunkStart, chunkEnd], not
 * just one — a chunk of 2-3 āyahs is graded as a single unit, matching how
 * the learner actually recited it. */
function clean(rep: ClipReport, chunkStart: number, chunkEnd: number, expectedWordCount: number): boolean {
  if (!rep.located || rep.content_status === "content_mismatch") return false;
  const words = rep.word_scores.filter((w) => w.ayah != null && w.ayah >= chunkStart && w.ayah <= chunkEnd);
  if (words.length === 0) return false;
  const complete = words.length >= expectedWordCount - 1;
  const ratio = words.filter((w) => w.content_ok).length / words.length;
  return complete && ratio >= PASS_RATIO;
}

function groupByAyah(words: AyahTaggedWordScore[]): Record<number, AyahTaggedWordScore[]> {
  const out: Record<number, AyahTaggedWordScore[]> = {};
  for (const w of words) {
    if (w.ayah == null) continue;
    (out[w.ayah] ??= []).push(w);
  }
  return out;
}

/** Interface spec §04.3 — Listen & Repeat. A 4-stage prompt-fading guided
 * flow (Listen -> Echo -> Recall -> Blind) over a CHUNK of 1-3 āyahs at a
 * time — the learner's own choice, not fixed at one. Reuses the same
 * paragraph-mode grading Practice.tsx already uses (gradeClip): a chunk is
 * just a bounded range within the sūrah, graded as one unit exactly like
 * "chaining" already worked for a single āyah spilling into the next
 * (§04.2) — no new grading logic needed, only tracking a range instead of
 * a single number. */
export default function ListenRepeat() {
  const { surah: surahParam } = useParams();
  const surah = Number(surahParam);

  const { data: surahs } = useSurahs();
  const { data: verses } = useVerses(surah);
  const { defaultReciter } = useSettings();
  const { data: audioTracks } = useAudio(surah, defaultReciter);
  const player = usePlayer();
  const { entries, recordReview, loading: memLoading } = useMemorization();
  const streak = useStreak();
  const slate = useActiveSlate();

  const info = surahs?.find((s) => s.surah === surah);

  const startAyah = useMemo(() => {
    if (!verses) return 1;
    const firstUnmastered = verses.find(
      (v) => entries.find((e) => e.surah === surah && e.ayah === v.ayah)?.status !== "mastered"
    );
    return firstUnmastered?.ayah ?? 1;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verses, surah]);

  // NOTE: chunkStart must not be seeded until memorization has actually
  // LOADED (below) — entries are async now (Supabase, not localStorage), and
  // seeding from the not-yet-loaded empty list would lock every session onto
  // āyah 1 even for a learner who already mastered 1-10.

  const [chunkStart, setChunkStart] = useState<number | null>(null);
  const [chunkSize, setChunkSize] = useState<number>(loadChunkSize);
  const [stage, setStage] = useState<Stage>("listen");
  const [blindStreak, setBlindStreak] = useState(0);
  const [blindFails, setBlindFails] = useState(0);
  const [fellBack, setFellBack] = useState(false);
  const [report, setReport] = useState<ClipReport | null>(null);
  const [grading, setGrading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionDone, setSessionDone] = useState(false);
  const [sessionConfirmed, setSessionConfirmed] = useState(0);
  const [sessionNeedsWork, setSessionNeedsWork] = useState(0);
  const advanceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    localStorage.setItem(CHUNK_SIZE_KEY, String(chunkSize));
  }, [chunkSize]);

  // Claim a slot the moment a guided session genuinely begins, same as
  // Sūrah Detail's "Recite now" — blocked up front if the slate is full.
  const [blocked, setBlocked] = useState(false);
  useEffect(() => {
    if (slate.isActive(surah)) return;
    if (!slate.claimSlot(surah)) setBlocked(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [surah]);

  useEffect(() => {
    if (chunkStart == null && verses && !memLoading) setChunkStart(startAyah);
  }, [chunkStart, verses, memLoading, startAyah]);

  useEffect(() => () => {
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
  }, []);

  const chunkEnd = useMemo(() => {
    if (chunkStart == null || !verses || verses.length === 0) return null;
    const lastAyah = verses[verses.length - 1].ayah;
    return Math.min(chunkStart + chunkSize - 1, lastAyah);
  }, [chunkStart, chunkSize, verses]);

  const chunkAyahs = useMemo(() => {
    if (chunkStart == null || chunkEnd == null || !verses) return [];
    return verses.filter((v) => v.ayah >= chunkStart && v.ayah <= chunkEnd);
  }, [chunkStart, chunkEnd, verses]);

  const expectedWordCount = useMemo(
    () => chunkAyahs.reduce((sum, v) => sum + v.text.split(/\s+/).filter(Boolean).length, 0),
    [chunkAyahs]
  );

  const resetChunkState = () => {
    setStage("listen");
    setBlindStreak(0);
    setBlindFails(0);
    setFellBack(false);
    setReport(null);
    setError(null);
  };

  const goToChunk = (start: number) => {
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
    setChunkStart(start);
    resetChunkState();
  };

  const finishChunk = () => {
    if (chunkStart == null || chunkEnd == null) return;
    const hadTrouble = fellBack || blindFails >= FALLBACK_AFTER_FAILS;
    const quality = hadTrouble ? 2 : blindFails > 0 ? 4 : 5;
    for (const v of chunkAyahs) recordReview(surah, v.ayah, quality);
    streak.recordActivity();
    if (hadTrouble) setSessionNeedsWork((n) => n + chunkAyahs.length);
    else setSessionConfirmed((n) => n + chunkAyahs.length);

    const nextStart = verses?.find((v) => v.ayah > chunkEnd)?.ayah;
    if (nextStart) {
      goToChunk(nextStart);
    } else {
      setSessionDone(true);
    }
  };

  const [noAudioTrack, setNoAudioTrack] = useState(false);
  const playChunk = () => {
    const tracks = chunkAyahs
      .map((v) => audioTracks?.find((t) => t.ayah === v.ayah))
      .filter((t): t is NonNullable<typeof t> => Boolean(t));
    if (tracks.length === 0) {
      setNoAudioTrack(true);
      return;
    }
    setNoAudioTrack(false);
    player.play(tracks, 0);
  };

  const handleSegment = async (blob: Blob) => {
    if (chunkStart == null || chunkEnd == null || stage === "listen") return;
    setGrading(true);
    setError(null);
    try {
      const wav = await blobToWav16kMono(blob);
      const rep = await gradeClip(surah, wav, chunkStart);

      // Discard segments with essentially no recognized speech BEFORE they
      // touch any state — not just "not passed", genuinely not a real
      // attempt. Belt-and-suspenders alongside the autoRec.stop() calls
      // below: those close the main gap (recorder left running after a
      // pass), but a fail intentionally keeps listening for an immediate
      // retry, and a reciter pausing to collect themselves before that retry
      // hits the exact same trailing-silence risk — a near-empty segment
      // would otherwise register as "another wrong attempt" purely from
      // background noise, inflating blindFails/echo-recall retries on
      // nothing the reciter actually said.
      if ((rep.decoded_text ?? "").trim().length < 3) return;

      setReport(rep);
      const passed = clean(rep, chunkStart, chunkEnd, expectedWordCount);

      // Every path that leads to a stage change stops the recorder
      // IMMEDIATELY, synchronously with the pass — not just after the
      // delayed setStage(). Otherwise useAutoRecorder keeps listening straight
      // through a correct recitation: the reciter goes quiet, but the mic
      // stays hot, and sooner or later background noise (or just the mic's
      // own noise floor) trips the pause detector's speech threshold again,
      // cutting a near-silent trailing segment that gets graded, fails (there
      // was nothing real in it), and overwrites the correct ✅ with a false
      // "Not quite" — exactly the "recite correctly, wait, then told wrong"
      // bug this comment exists to prevent regressing.
      if (stage === "echo") {
        if (passed) {
          autoRec.stop();
          advanceTimer.current = setTimeout(() => setStage("recall"), ADVANCE_DELAY_MS);
        }
        return;
      }
      if (stage === "recall") {
        if (passed) {
          autoRec.stop();
          advanceTimer.current = setTimeout(() => setStage("blind"), ADVANCE_DELAY_MS);
        }
        return;
      }
      // stage === "blind". Stop on EVERY pass here, not just the one that
      // hits BLIND_STREAK_TARGET — leaving the recorder running between the
      // 1st and 2nd clean attempt reintroduces the exact "still recording"
      // bug fixed above, just one level down: the reciter pauses after a
      // correct 1st attempt to collect themselves before the 2nd, the mic
      // stays hot through that pause, a trailing-silence segment eventually
      // gets cut and graded, fails, and silently resets blindStreak back to
      // 0 in the `else` branch below — before the reciter even gets to
      // attempt the second recitation. Symptom: streak never advances past
      // 1, reads as "the second recitation isn't working."
      if (passed) {
        autoRec.stop();
        const nextStreak = blindStreak + 1;
        setBlindStreak(nextStreak);
        if (nextStreak >= BLIND_STREAK_TARGET) {
          advanceTimer.current = setTimeout(finishChunk, ADVANCE_DELAY_MS);
        }
      } else {
        setBlindStreak(0);
        const fails = blindFails + 1;
        setBlindFails(fails);
        if (fails >= FALLBACK_AFTER_FAILS) {
          setFellBack(true);
          autoRec.stop();
          advanceTimer.current = setTimeout(() => setStage("recall"), ADVANCE_DELAY_MS);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Grading failed.");
    } finally {
      setGrading(false);
    }
  };

  const autoRec = useAutoRecorder(handleSegment);
  const wordsByAyah = useMemo(() => (report ? groupByAyah(report.word_scores) : {}), [report]);

  if (!isCorrectionConfigured) {
    return (
      <div className="p-6">
        <h1 className="text-xl font-bold">Listen &amp; Repeat</h1>
        <div className="mt-4 rounded-xl bg-amber-500/15 p-4 text-sm text-amber-800 dark:text-amber-300">
          The correction service isn’t configured. Start the API
          (<code>server/run.ps1</code>) and set{" "}
          <code>VITE_CORRECTION_API_URL</code> in <code>app/.env.local</code>,
          then restart the dev server.
        </div>
      </div>
    );
  }

  if (blocked) {
    return (
      <div className="p-6 pb-24">
        <Link to={`/surah/${surah}`} className="text-sm text-brand-muted dark:text-brand-darkMuted">← Back</Link>
        <p className="mt-6 text-center text-sm text-brand-red">
          Your active slate is full — step back from another sūrah or finish one first (§06).
        </p>
      </div>
    );
  }

  if (!info || !verses || chunkStart == null || chunkEnd == null || chunkAyahs.length === 0) {
    return <div className="p-6"><Spinner label="Loading…" /></div>;
  }

  if (sessionDone) {
    return (
      <SessionSummary
        ratio={memorizedRatio(surah, info.ayah_count, entries)}
        confirmed={sessionConfirmed}
        needsWork={sessionNeedsWork}
        streakDays={streak.current}
        keepGoingTo={`/surah/${surah}`}
        keepGoingLabel={`Back to ${info.name_tr}`}
        backTo="/"
      />
    );
  }

  return (
    <div className="pb-24">
      <header className="bg-brand-emerald px-5 pb-5 pt-8 text-white">
        <Link to={`/surah/${surah}`} className="text-sm text-white/70">← {info.name_tr}</Link>
        <h1 className="mt-2 text-xl font-bold">Listen &amp; Repeat</h1>
        <p className="mt-0.5 text-sm text-white/80">
          Āyah {chunkEnd > chunkStart ? `${chunkStart}–${chunkEnd}` : chunkStart} of {verses.length}
        </p>
      </header>

      {/* Stage row */}
      <div className="flex justify-center gap-2 px-5 py-4">
        {STAGES.map((s, i) => {
          const doneIdx = STAGES.indexOf(stage);
          const state = i < doneIdx ? "done" : s === stage ? "current" : "upcoming";
          return (
            <span
              key={s}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                state === "done"
                  ? "bg-brand-emerald/15 text-brand-emerald"
                  : state === "current"
                  ? "bg-brand-emerald text-white"
                  : "bg-brand-muted/10 text-brand-muted dark:text-brand-darkMuted"
              }`}
            >
              {STAGE_LABEL[s]}
            </span>
          );
        })}
      </div>

      {/* Chunk size — the learner's own choice, only adjustable before a
          chunk's recording actually starts (changing it mid-Echo/Recall/
          Blind would be confusing — you're already committed to this one). */}
      {stage === "listen" && (
        <div className="mb-1 flex items-center justify-center gap-2">
          <span className="text-xs text-brand-muted dark:text-brand-darkMuted">Āyahs at a time:</span>
          {CHUNK_SIZES.map((n) => (
            <button
              key={n}
              onClick={() => setChunkSize(n)}
              className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                chunkSize === n
                  ? "bg-brand-emerald text-white"
                  : "border border-brand-muted/25 text-brand-muted dark:border-brand-darkMuted/25 dark:text-brand-darkMuted"
              }`}
            >
              {n}
            </button>
          ))}
        </div>
      )}

      {/* Starting āyah — the learner chooses where to begin / continue from
          (defaults to the first āyah they haven't mastered). Only before a
          chunk's recording starts, same as the chunk-size control. */}
      {stage === "listen" && (
        <div className="mt-1 flex items-center justify-center gap-2">
          <label htmlFor="start-ayah" className="text-xs text-brand-muted dark:text-brand-darkMuted">
            Start from āyah:
          </label>
          <select
            id="start-ayah"
            value={chunkStart}
            onChange={(e) => goToChunk(Number(e.target.value))}
            className="rounded-lg border border-brand-muted/25 bg-transparent px-2 py-1 text-xs font-semibold outline-none focus:border-brand-emerald"
          >
            {verses.map((v) => {
              const mastered =
                entries.find((e) => e.surah === surah && e.ayah === v.ayah)?.status === "mastered";
              return (
                <option key={v.ayah} value={v.ayah}>
                  {v.ayah}
                  {mastered ? " ✓" : ""}
                </option>
              );
            })}
          </select>
        </div>
      )}

      <div className="px-5">
        {/* The chunk itself — hidden during Blind */}
        <div className="rounded-2xl border border-brand-muted/15 p-6 text-center" dir="rtl">
          {stage === "blind" ? (
            <div className="flex flex-col items-center gap-2 py-6">
              <span className="text-3xl">🔒</span>
              <p className="quran text-sm text-brand-muted" dir="ltr">Recite from memory — no peeking.</p>
            </div>
          ) : (
            <GradedSurah verses={chunkAyahs} wordsByAyah={wordsByAyah} cursorAyah={-1} />
          )}
        </div>

        {stage === "blind" && (
          <div className="mt-3 flex justify-center gap-2">
            {Array.from({ length: BLIND_STREAK_TARGET }).map((_, i) => (
              <span
                key={i}
                className={`h-2.5 w-2.5 rounded-full ${
                  i < blindStreak ? "bg-brand-emerald" : "bg-brand-muted/20"
                }`}
              />
            ))}
          </div>
        )}

        {/* Stage controls */}
        <div className="mt-6 flex flex-col items-center gap-3">
          {stage === "listen" ? (
            <>
              <button
                onClick={playChunk}
                className="rounded-full bg-brand-emerald px-8 py-4 font-semibold text-white shadow-soft"
              >
                ▶ Play {chunkAyahs.length > 1 ? "these āyahs" : "this āyah"}
              </button>
              <button
                onClick={() => setStage("echo")}
                className="text-sm text-brand-emerald underline"
              >
                I've heard it — Echo →
              </button>
              {noAudioTrack && (
                <p className="text-sm text-brand-red">
                  No recitation on file for this range with the current reciter — try a different one in Settings, or skip ahead to Echo.
                </p>
              )}
              {player.error && <p className="text-sm text-brand-red">{player.error}</p>}
            </>
          ) : (
            <>
              {!autoRec.listening ? (
                <button
                  onClick={autoRec.start}
                  className="rounded-full bg-brand-emerald px-8 py-4 font-semibold text-white shadow-soft"
                >
                  🎙 Start reciting
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
                  <p className="text-xs text-brand-muted dark:text-brand-darkMuted">
                    {grading ? "Checking…" : `Listening — recite ${chunkAyahs.length > 1 ? "this passage" : "this āyah"}.`}
                  </p>
                </div>
              )}
              {report && !grading && (
                clean(report, chunkStart, chunkEnd, expectedWordCount) ? (
                  <p className="text-sm text-brand-emerald">✅ Correct.</p>
                ) : (
                  <p className="text-sm text-brand-red">Not quite — still listening, try again.</p>
                )
              )}
              {autoRec.error && <p className="text-sm text-brand-red">{autoRec.error}</p>}
              {error && <p className="text-sm text-brand-red">{error}</p>}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
