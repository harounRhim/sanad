import { useMemo } from "react";
import type { Verse } from "../lib/types";
import type { AyahTaggedWordScore } from "../lib/correction";
import { VERDICT_COLOR } from "../lib/grading";

const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";
function toArabicDigits(n: number): string {
  return String(n)
    .split("")
    .map((d) => ARABIC_DIGITS[Number(d)] ?? d)
    .join("");
}

interface Props {
  verses: Verse[];
  /** Latest known word-level verdicts per āyah number (merged in from
   * successive /grade_clip responses — see Practice.tsx). Āyahs with no
   * entry yet render as plain, uncolored text. */
  wordsByAyah: Record<number, AyahTaggedWordScore[]>;
  /** The āyah currently being listened for — given a soft highlight so the
   * reciter can see where the app thinks they are. */
  cursorAyah: number;
  /** "Recite from memory" mode (Practice's Recite-now flow): words with no
   * verdict yet render TRANSPARENT — invisible, but still occupying their
   * exact space so nothing reflows as words reveal. Each word appears (in its
   * graded color) only once the reciter has said it. Default false: Listen &
   * Repeat / Review keep showing the text to read from. */
  hideUngraded?: boolean;
  /** Clue reveal (only meaningful with hideUngraded): per-āyah number of
   * LEADING characters to un-hide as a soft "ghost" prompt — the opening of
   * the next āyah when the reciter blanks on how it starts. */
  hintChars?: Record<number, number>;
}

type Mode = "graded" | "plain" | "hint" | "hidden";
interface Run {
  text: string;
  w: AyahTaggedWordScore | null;
  mode: Mode;
}

/** Continuous "muṣḥaf book" rendering of a whole sūrah: every āyah flows as
 * part of ONE paragraph (not one boxed row per āyah — see the user's ask,
 * 2026-07-07), each word colored by its latest verdict, with a small inline
 * ayah-end marker after each āyah like real Qur'an typesetting. */
export default function GradedSurah({
  verses,
  wordsByAyah,
  cursorAyah,
  hideUngraded = false,
  hintChars,
}: Props) {
  const ayahRuns = useMemo(
    () =>
      verses.map((v) => {
        const words = wordsByAyah[v.ayah] ?? [];
        const at: (AyahTaggedWordScore | null)[] = new Array(v.text.length).fill(null);
        for (const w of words) {
          const end = Math.min(w.end_idx, v.text.length);
          for (let i = w.start_idx; i < end; i++) at[i] = w;
        }
        const hint = hintChars?.[v.ayah] ?? 0;
        // Per-char render mode: graded (has a verdict) → colored; else if the
        // text is shown (not hideUngraded) → plain ink; else if within the
        // clue's revealed opening → ghost; else → hidden (transparent).
        const modeOf = (i: number, w: AyahTaggedWordScore | null): Mode => {
          if (w) return "graded";
          if (!hideUngraded) return "plain";
          if (i < hint) return "hint";
          return "hidden";
        };
        const runs: Run[] = [];
        let cur: Run | null = null;
        for (let i = 0; i < v.text.length; i++) {
          const w = at[i];
          const mode = modeOf(i, w);
          if (!cur || cur.w !== w || cur.mode !== mode) {
            cur = { text: v.text[i], w, mode };
            runs.push(cur);
          } else cur.text += v.text[i];
        }
        return { verse: v, runs };
      }),
    [verses, wordsByAyah, hideUngraded, hintChars]
  );

  const titleFor = (w: AyahTaggedWordScore) => {
    if (!w.content_ok) return "Not recognized — check the word and pronunciation.";
    if (w.rules.length === 0) return "Correct.";
    return w.rules.map((r) => `${r.rule}: ${r.message}`).join("\n");
  };

  return (
    <p className="quran text-3xl leading-loose text-justify" dir="rtl">
      {ayahRuns.map(({ verse: v, runs }) => (
        <span
          key={`${v.surah}-${v.ayah}`}
          className={v.ayah === cursorAyah ? "rounded bg-brand-emerald/10" : undefined}
        >
          {runs.map((run, i) => {
            if (run.mode === "graded" && run.w) {
              return (
                <span
                  key={i}
                  style={{
                    color: VERDICT_COLOR[run.w.verdict],
                    borderBottom: `2px solid ${VERDICT_COLOR[run.w.verdict]}`,
                  }}
                  title={titleFor(run.w)}
                >
                  {run.text}
                </span>
              );
            }
            if (run.mode === "hint") {
              // Clue prompt — soft gold, not a graded color, so it reads as
              // "here's how it starts", not "you said this".
              return (
                <span key={i} style={{ color: "#C9A227", opacity: 0.7 }} title="Clue">
                  {run.text}
                </span>
              );
            }
            if (run.mode === "hidden") {
              // Transparent keeps the glyph's box so nothing shifts when it
              // reveals; select-none so the hidden text can't be copy-peeked.
              return (
                <span key={i} className="select-none" style={{ color: "transparent" }}>
                  {run.text}
                </span>
              );
            }
            return <span key={i}>{run.text}</span>; // plain ink (text shown)
          })}
          <span className="mx-1 text-lg text-brand-gold">﴿{toArabicDigits(v.ayah)}﴾</span>{" "}
        </span>
      ))}
    </p>
  );
}
