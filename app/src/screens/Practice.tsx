import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useSurahs, useVerses } from "../hooks/useQueries";
import { useRollingRecorder } from "../hooks/useRollingRecorder";
import { gradeClip, isCorrectionConfigured, type AyahTaggedWordScore } from "../lib/correction";
import Spinner from "../components/Spinner";
import GradedSurah from "../components/GradedSurah";

type AyahStatus = "pass" | "needs_work";

const MAX_SURAH = 114;
const PASS_RATIO = 0.5;   // majority of a located āyah's words content_ok -> "pass"
// A clue reveals the opening WORDS of the NEXT āyah — the one you're about to
// recite but can't recall the start of. Reciting already shows the CURRENT
// āyah's words as you say them, so the clue's real job is un-blanking the
// beginning of the next one. Each tap reveals one more word (progressive, so
// it scales to however stuck you are — short nudge or a longer run-up).
const CLUE_WORDS_PER_TAP = 1;

/** Char index just past the first `n` whitespace-delimited words of `text`. */
function firstWordsCharLen(text: string, n: number): number {
  let i = 0;
  let words = 0;
  while (i < text.length && words < n) {
    while (i < text.length && /\s/.test(text[i])) i++;   // skip spaces
    while (i < text.length && !/\s/.test(text[i])) i++;  // consume a word
    words++;
  }
  return i;
}

export default function Practice() {
  const [params, setParams] = useSearchParams();
  const surah = Math.min(Math.max(Number(params.get("surah")) || 1, 1), MAX_SURAH);

  const { data: surahs } = useSurahs();
  const { data: verses } = useVerses(surah);
  const surahInfo = surahs?.find((s) => s.surah === surah);

  // Roadmap V2 (2026-07-08) — "a sūrah is just a paragraph, no navigating
  // between āyahs". Each graded window is checked STATELESSLY against the
  // WHOLE sūrah (server: evaluate_clip / content_check.locate_best_span) —
  // no āyah/cursor is sent, the server figures out where the audio's content
  // falls. This replaced an earlier cursor-driven window design that kept
  // getting stuck: if one confirmation failed, every later clip (containing
  // genuinely later content) kept comparing against the same un-advanced
  // window start and could never match either. There's no cursor here to
  // get stuck in the first place — `highlightAyah` below is purely cosmetic
  // (which āyah to softly highlight), not an input to grading.
  const [highlightAyah, setHighlightAyah] = useState(1);
  const [wordsByAyah, setWordsByAyah] = useState<Record<number, AyahTaggedWordScore[]>>({});
  // Mirrors `wordsByAyah` but read/written synchronously within handleWindow
  // (state updates are async) -- see the sticky-merge comment there.
  const wordsByAyahRef = useRef<Record<number, AyahTaggedWordScore[]>>({});
  const [ayahStatus, setAyahStatus] = useState<Record<number, AyahStatus>>({});
  const [mismatch, setMismatch] = useState<string | null>(null);
  const [gradingCount, setGradingCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Temporary diagnostic log (2026-07-08) — the mic loop can't be exercised
  // in the dev sandbox that builds this app, so this on-screen trace is how
  // the user reports back exactly what's happening (windows graded, latency,
  // results) without needing browser dev tools. Safe to remove once
  // continuous recitation is confirmed working reliably in real use.
  const [log, setLog] = useState<string[]>([]);
  const addLog = (msg: string) =>
    setLog((l) => [...l.slice(-9), `${new Date().toLocaleTimeString()}  ${msg}`]);

  const goToSurah = (s: number) => {
    setParams({ surah: String(Math.min(Math.max(s, 1), MAX_SURAH)) });
  };

  const jumpTo = (ayah: number) => {
    setMismatch(null);
    setHighlightAyah(ayah);
  };

  // Fires on a fixed timer (~every 1.7s) with the trailing ~3.2s of audio —
  // see useRollingRecorder for why this is a SLIDING window rather than a
  // pause-triggered cut (the previous design's several-second lag before
  // anything colored, reported as "not live"). The blob arrives already
  // resampled to 16kHz mono, ready to POST directly. Defined fresh every
  // render (not memoized) so it always closes over the CURRENT
  // `surah`/`verses`; useRollingRecorder re-reads it via a ref on every
  // render, so this is safe even though the mic callback fires later.
  const handleWindow = async (wav: Blob) => {
    const t0 = performance.now();
    addLog(`grading ~3.2s window (${(wav.size / 1024).toFixed(0)} KB) — locating in sūrah ${surah}…`);
    setGradingCount((n) => n + 1);
    setError(null);
    setMismatch(null);
    try {
      const rep = await gradeClip(surah, wav, highlightAyah);
      const ms = Math.round(performance.now() - t0);

      if (!rep.located || rep.ayah_from == null || rep.ayah_to == null) {
        addLog(`→ not recognized (${ms}ms) — heard: "${rep.decoded_text}"`);
        setMismatch(rep.decoded_text);
        return;
      }
      const redWords = rep.word_scores.filter((w) => !w.content_ok).map((w) => w.word);
      addLog(
        `→ located ${surah}:${rep.ayah_from}${rep.ayah_to !== rep.ayah_from ? `-${rep.ayah_to}` : ""} (${ms}ms) — heard: "${rep.decoded_text}"` +
          (redWords.length > 0 ? ` — red: ${redWords.join(", ")}` : "")
      );

      const grouped: Record<number, AyahTaggedWordScore[]> = {};
      for (const w of rep.word_scores) {
        if (w.ayah != null) (grouped[w.ayah] ??= []).push(w);
      }

      // Sticky merge, per word (matched by its position within the āyah —
      // stable across rolling windows since score_words always splits the
      // same reference text the same way). A rolling window is graded fresh
      // and independently every ~1.7s, and its framing can occasionally cut
      // a word awkwardly and mis-grade something that was already confirmed
      // correct moments ago — wholesale-replacing an āyah's words on every
      // response caused exactly the flicker the user reported ("sometimes
      // it makes the words green then it changes it to red"). Once a word
      // is written down correct, it stays correct — like committing to a
      // paragraph instead of re-transcribing it from scratch every pass.
      // Never downgrades green->red, but a fresh green still overwrites an
      // old red (upgrades are real progress, not noise).
      // UNION with the previous round, not a replace — a later rolling
      // window can legitimately stop covering an EARLIER word once the
      // window has slid past it (the server now excludes words a clip
      // never reached rather than guessing red, see word_score.py's
      // NOT_REACHED_SLACK) — if that excluded word isn't unioned back in
      // here, it would silently vanish from the display even though it was
      // already correctly confirmed a moment ago.
      const mergedThisRound: Record<number, AyahTaggedWordScore[]> = {};
      for (const [ayahStr, newWords] of Object.entries(grouped)) {
        const ayah = Number(ayahStr);
        const byStart = new Map((wordsByAyahRef.current[ayah] ?? []).map((w) => [w.start_idx, w]));
        for (const w of newWords) {
          const old = byStart.get(w.start_idx);
          byStart.set(w.start_idx, old && old.content_ok && !w.content_ok ? old : w);
        }
        mergedThisRound[ayah] = Array.from(byStart.values()).sort((a, b) => a.start_idx - b.start_idx);
      }
      wordsByAyahRef.current = { ...wordsByAyahRef.current, ...mergedThisRound };
      setWordsByAyah(wordsByAyahRef.current);

      setAyahStatus((prev) => {
        const next = { ...prev };
        for (const [ayahStr, words] of Object.entries(mergedThisRound)) {
          const ayah = Number(ayahStr);
          const ratio = words.filter((w) => w.content_ok).length / words.length;
          // Words the clip never reached are EXCLUDED, not marked red (see
          // word_score.py's NOT_REACHED_SLACK) — an āyah only partway
          // through being recited must not read as "pass" from just its
          // first couple of (correct) words, so require the word count
          // seen SO FAR to be close to the āyah's actual total too.
          const expected =
            verses?.find((v) => v.ayah === ayah)?.text.split(/\s+/).filter(Boolean).length ?? 0;
          const complete = words.length >= expected - 1;
          next[ayah] = complete && ratio >= PASS_RATIO ? "pass" : "needs_work";
        }
        return next;
      });

      // Practice is FREE REHEARSAL (decided 2026-07-12): it deliberately does
      // NOT write memorization / streak / SRS state and does NOT claim a slate
      // slot. Listen & Repeat is the sole path that advances ḥifẓ progress and
      // enforces the 6-slot cap — otherwise reciting here would silently bypass
      // it. The word-level coloring below is in-session feedback only.

      setHighlightAyah(rep.ayah_to);
      // No auto-advance to the next sūrah — the user asked to see their
      // finished progress (all-green dots, full coloring) rather than have
      // the screen reset out from under them the instant the last āyah
      // passes. `surahComplete` below (derived from `ayahStatus`) shows a
      // completion banner with a manual "Next sūrah" button instead.
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Grading failed.";
      addLog(`✗ error: ${msg}`);
      setError(msg);
    } finally {
      setGradingCount((n) => n - 1);
    }
  };

  const autoRec = useRollingRecorder(handleWindow);

  // Reset per-sūrah state whenever the sūrah itself changes (new session).
  // Deliberately does NOT touch the recorder — it keeps listening seamlessly
  // across a sūrah rollover, same as across an āyah advance.
  useEffect(() => {
    setHighlightAyah(1);
    wordsByAyahRef.current = {};
    setWordsByAyah({});
    setAyahStatus({});
    setMismatch(null);
    setError(null);
    setHint(null);
  }, [surah]);

  // --- Clue: reveal the start of the NEXT āyah -------------------------------
  // The next āyah to recite = the first one not yet passed. `hint` holds how
  // many of its opening words to un-hide (ghost text); each tap reveals one
  // more. Cleared when that āyah gets recited (nextAyah moves on) or the sūrah
  // changes.
  const [hint, setHint] = useState<{ ayah: number; words: number } | null>(null);

  const nextAyah = useMemo(() => {
    if (!verses) return null;
    const v = verses.find((x) => ayahStatus[x.ayah] !== "pass");
    return v?.ayah ?? null;
  }, [verses, ayahStatus]);

  const revealClue = () => {
    if (nextAyah == null) return;
    setHint((h) =>
      h && h.ayah === nextAyah
        ? { ayah: nextAyah, words: h.words + CLUE_WORDS_PER_TAP }
        : { ayah: nextAyah, words: CLUE_WORDS_PER_TAP }
    );
  };

  // Drop a stale hint once its āyah is recited (or the sūrah changes below).
  useEffect(() => {
    setHint((h) => (h && h.ayah !== nextAyah ? null : h));
  }, [nextAyah]);

  // Per-āyah count of leading CHARACTERS to reveal, derived from the word hint.
  const hintChars = useMemo(() => {
    if (!hint || !verses) return {} as Record<number, number>;
    const v = verses.find((x) => x.ayah === hint.ayah);
    if (!v) return {} as Record<number, number>;
    return { [hint.ayah]: firstWordsCharLen(v.text, hint.words) };
  }, [hint, verses]);

  // Every āyah confirmed correct -> the sūrah is done. Derived straight from
  // `ayahStatus` (not tracked separately) so it stays in sync automatically.
  const surahComplete =
    verses != null && verses.length > 0 && verses.every((v) => ayahStatus[v.ayah] === "pass");

  if (!isCorrectionConfigured) {
    return (
      <div className="p-6">
        <h1 className="text-xl font-bold">Check my recitation</h1>
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
      <h1 className="text-xl font-bold">Check my recitation</h1>
      <p className="mt-1 text-sm text-brand-muted">
        Free practice — recite any sūrah, any time. I check word by word in the
        background every couple of seconds, no button-pressing needed. This is
        just rehearsal; it won’t change your memorization progress.
      </p>
      <div className="mt-1 flex flex-col gap-1">
        <Link to="/" className="inline-block text-sm text-brand-emerald underline">
          📿 Tracking your ḥifẓ? Use Listen &amp; Repeat on the Journey →
        </Link>
        <Link to="/drills" className="inline-block text-sm text-brand-emerald underline">
          🎯 Practice one tajweed rule at a time instead →
        </Link>
      </div>

      {/* Surah picker */}
      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={() => goToSurah(surah - 1)}
          disabled={surah <= 1}
          className="rounded-lg border border-brand-muted/30 px-3 py-2 text-sm disabled:opacity-40"
        >
          ‹
        </button>
        <select
          value={surah}
          onChange={(e) => goToSurah(Number(e.target.value))}
          className="flex-1 rounded-lg border border-brand-muted/30 bg-transparent px-3 py-2 text-sm"
        >
          {surahs?.map((s) => (
            <option key={s.surah} value={s.surah}>
              {s.surah}. {s.name_tr}
            </option>
          ))}
        </select>
        <button
          onClick={() => goToSurah(surah + 1)}
          disabled={surah >= MAX_SURAH}
          className="rounded-lg border border-brand-muted/30 px-3 py-2 text-sm disabled:opacity-40"
        >
          ›
        </button>
      </div>
      {surahInfo && (
        <div className="mt-2 flex items-center justify-between text-sm text-brand-muted">
          <span>{surahInfo.ayah_count} āyahs</span>
          <span className="quran text-lg" dir="rtl">{surahInfo.name_ar}</span>
        </div>
      )}

      {/* Progress strip — tap a dot to jump the highlight to that āyah */}
      {verses && verses.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {verses.map((v) => {
            const st = ayahStatus[v.ayah];
            const bg =
              v.ayah === highlightAyah
                ? "#0E5A4A"
                : st === "pass"
                ? "#2BB673"
                : st === "needs_work"
                ? "#E5392B"
                : "#D8D3C4";
            return (
              // Visual dot stays 10px; the BUTTON is a 28px padded hit area
              // (negative margin keeps the strip visually dense) — bare 10px
              // targets are un-tappable on the phones most sessions run on.
              <button
                key={v.ayah}
                onClick={() => jumpTo(v.ayah)}
                title={`${v.surah}:${v.ayah}`}
                aria-label={`Jump to āyah ${v.ayah}`}
                className="-m-1.5 flex h-7 w-7 items-center justify-center"
              >
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: bg }} />
              </button>
            );
          })}
        </div>
      )}

      {surahComplete && (
        <div className="mt-3 flex flex-col items-center gap-2 rounded-xl bg-brand-emerald/15 p-3 text-center">
          <p className="text-sm font-semibold text-brand-emerald">
            🎉 Well done — you finished this sūrah correctly!
          </p>
          {surah < MAX_SURAH && (
            <button
              onClick={() => goToSurah(surah + 1)}
              className="rounded-full bg-brand-emerald px-5 py-2 text-sm font-semibold text-white shadow-soft"
            >
              Next sūrah →
            </button>
          )}
        </div>
      )}

      {/* Continuous listening controls */}
      <div className="mt-4 flex flex-col items-center gap-2">
        {!autoRec.listening ? (
          <button
            onClick={autoRec.start}
            disabled={!verses || verses.length === 0}
            className="rounded-full bg-brand-emerald px-8 py-4 font-semibold text-white shadow-soft disabled:opacity-50"
          >
            🎙 Start reciting this sūrah
          </button>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <button
              onClick={autoRec.stop}
              className="flex items-center gap-2 rounded-full bg-brand-red px-8 py-4 text-white shadow-soft"
            >
              <span className="h-3 w-3 animate-pulse rounded-full bg-white" />
              Stop listening
            </button>
            <div className="h-1.5 w-40 overflow-hidden rounded-full bg-brand-muted/20">
              <div
                className="h-full bg-brand-emerald transition-[width]"
                style={{ width: `${Math.min(100, autoRec.volume * 400)}%` }}
              />
            </div>
            <p className="text-xs text-brand-muted">
              {gradingCount > 0
                ? "Listening — checking what you just said…"
                : "Listening — recite naturally, at your own pace."}
            </p>
          </div>
        )}

        {/* Clue — un-blank the START of the next āyah when memory stalls.
            Each tap shows one more of its opening words (as ghost text). */}
        {nextAyah != null && (
          <button
            onClick={revealClue}
            className="mt-1 inline-flex items-center gap-1.5 rounded-full border border-brand-gold/50 px-5 py-2 text-sm font-semibold text-brand-gold transition-colors hover:bg-brand-gold/10 dark:text-brand-goldLight"
          >
            {hint && hint.ayah === nextAyah
              ? "💡 Show one more word"
              : `💡 Clue — reveal the start of āyah ${nextAyah}`}
          </button>
        )}

        {mismatch && (
          <div className="w-full rounded-xl bg-amber-500/15 p-3 text-center text-sm text-amber-800 dark:text-amber-300">
            This didn’t sound like this sūrah — still listening, try again.
            <div className="mt-1 text-xs opacity-80" dir="rtl">We heard: {mismatch}</div>
          </div>
        )}
        {autoRec.error && <p className="text-sm text-brand-red">{autoRec.error}</p>}
        {error && <p className="text-sm text-brand-red">{error}</p>}
      </div>

      {/* The WHOLE sūrah as one continuous "muṣḥaf" flow, not a row per āyah.
          Words are ALWAYS hidden here (recite from memory) and each appears in
          its graded color as it's recited. No read-along peek on purpose — to
          read the text, the Read page is one tap away. */}
      {!verses ? (
        <div className="mt-6"><Spinner label="Loading sūrah…" /></div>
      ) : (
        <div className="mt-6 rounded-2xl border border-brand-muted/15 p-5">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-xs text-brand-muted">Reciting from memory</span>
            <Link
              to={`/read/${surah}`}
              className="text-xs font-semibold text-brand-emerald underline dark:text-brand-goldLight"
            >
              Read the text →
            </Link>
          </div>
          <GradedSurah
            verses={verses}
            wordsByAyah={wordsByAyah}
            cursorAyah={highlightAyah}
            hideUngraded
            hintChars={hintChars}
          />
          {Object.keys(wordsByAyah).length === 0 && (
            <p className="mt-3 text-center text-xs text-brand-muted dark:text-brand-darkMuted">
              Recite from memory — each word appears as you say it. Stuck on the
              next āyah? Tap “Clue” to peek its opening.
            </p>
          )}
        </div>
      )}

      {/* Legend of colors used (word-level verdict, Roadmap V2 Phase 1) */}
      {Object.keys(wordsByAyah).length > 0 && (
        <div className="mt-6 flex justify-center gap-4 text-xs text-brand-muted">
          <span>🟢 correct</span>
          <span>🟠 tajweed needs work</span>
          <span>🔴 word not recognized</span>
        </div>
      )}

      {/* Temporary diagnostic log — see comment near `log` state above.
          Deliberately NOT gated on autoRec.listening so it survives after
          Stop is pressed — otherwise it vanishes right when you need to
          read it back. DEV-only: real users must never see a debug trace
          (dev server still shows it, which is where mic testing happens). */}
      {import.meta.env.DEV && log.length > 0 && (
        <div className="mt-6 rounded-lg bg-black/5 p-3 font-mono text-[11px] leading-relaxed text-brand-muted dark:bg-white/5">
          <p className="mb-1 font-sans font-semibold">Activity log (debug)</p>
          {log.length === 0 ? (
            <p>Waiting for enough audio to grade the first window…</p>
          ) : (
            log.map((line, i) => <p key={i}>{line}</p>)
          )}
        </div>
      )}
    </div>
  );
}
