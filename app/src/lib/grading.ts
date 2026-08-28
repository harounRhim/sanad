import type { GradeReport, WordScore } from "./correction";

export const STATUS_COLOR: Record<string, string> = {
  ok: "#2BB673",
  warn: "#E8A33D",
  missing_audio: "#9AA0A6",
};

/** Roadmap V2 Phase 1 — combined content+tajweed verdict per word. */
export const VERDICT_COLOR: Record<WordScore["verdict"], string> = {
  green: "#2BB673",
  yellow: "#E8A33D",
  red: "#E5392B",
};

/** An āyah "passes" (auto-advances to the next one) when its content was
 * recognized and no word was misrecognized — tajweed nuances (yellow) are
 * shown as feedback but don't block moving on, only wrong/missing words do.
 * Shared between Practice.tsx (whole-page recitation) and Drills.tsx
 * (per-rule practice), both driven by the same continuous auto-recorder. */
export function ayahPassed(rep: GradeReport): boolean {
  return (
    rep.content_status !== "content_mismatch" &&
    !rep.word_scores.some((w) => w.verdict === "red")
  );
}

/**
 * Rules Report.results actually grades (rules.py's v1 coverage — Madd +
 * Ghunnah family). The other 8 of the 18 TAJWEED_RULES (qalqalah,
 * hamzat_wasl, lam_shamsiyyah, silent, idghaam_no_ghunnah/shafawi/
 * mutajanisayn/mutaqaribayn) have no acoustic measurement yet — drilling them
 * would always come back "no rules to grade", so the drills screen excludes
 * them rather than offering a drill that can't actually give feedback.
 */
export const GRADABLE_RULES = new Set([
  "madd_2", "madd_muttasil", "madd_munfasil", "madd_6", "madd_246",
  "ghunnah", "idghaam_ghunnah", "ikhfa", "iqlab", "ikhfa_shafawi",
]);

/**
 * SM-2 "recall quality" (0-5) derived from a real grading result instead of
 * a manual self-rating (Roadmap V2 Phase 5 — the payoff for building Phases
 * 0/1 first). Only ever returns 5, 4, or 2 today:
 *   5 = every word green (perfect, no tajweed notes at all)
 *   4 = content recognized, no wrong words, but at least one tajweed "warn"
 *       (SM-2's own neutral quality — keeps the ease factor unchanged)
 *   2 = any word misrecognized (below SM-2's quality>=3 "successful recall"
 *       threshold — resets the repetition streak, same as a manual "Again")
 * content_mismatch is NOT handled here — callers should skip SRS scheduling
 * entirely for that case (see Practice.tsx), same reasoning as Phase 4's
 * memorization tracker: an ambiguous attempt shouldn't reset a real schedule.
 */
export function srsQualityForWords(words: Pick<WordScore, "verdict">[]): number {
  if (words.some((w) => w.verdict === "red")) return 2;
  if (words.some((w) => w.verdict === "yellow")) return 4;
  return 5;
}

export function srsQuality(rep: GradeReport): number {
  return srsQualityForWords(rep.word_scores);
}
