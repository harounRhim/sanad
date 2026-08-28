/**
 * Pure SM-2 spaced-repetition scheduler (Roadmap V2 Phase 5). Framework-free
 * so it can be reasoned about independently of when/how a review happens —
 * Review.tsx just calls `applySM2` with a quality score and persists the
 * result via useMemorization.
 *
 * Reference: the classic SuperMemo SM-2 algorithm. Quality is 0-5 (this app
 * only ever produces 5/4/2 today — see srsQuality() in lib/grading.ts, which
 * derives it from real grading instead of a manual self-rating, per the
 * roadmap's whole point in building Phases 1/4 first — but the algorithm
 * itself supports the full 0-5 range for future manual Again/Hard/Good/Easy
 * buttons if ever added as a fallback).
 */

export interface SRSState {
  easeFactor: number;   // >= 1.3, starts at 2.5
  intervalDays: number; // days until the NEXT review after this one
  repetitions: number;  // consecutive successful (quality >= 3) reviews
}

export const INITIAL_SRS_STATE: SRSState = {
  easeFactor: 2.5,
  intervalDays: 0,
  repetitions: 0,
};

const MIN_EASE_FACTOR = 1.3;

/**
 * One SM-2 step. `quality` >= 3 counts as a successful recall (interval
 * grows); < 3 resets repetitions and drops the interval back to 1 day,
 * regardless of how "close" the miss was — SM-2's whole premise is that a
 * failed recall means the schedule was too optimistic.
 */
export function applySM2(prev: SRSState, quality: number, nowMs: number): SRSState & { nextReviewAt: number } {
  const q = Math.max(0, Math.min(5, quality));

  let { easeFactor, repetitions } = prev;
  let intervalDays: number;

  if (q >= 3) {
    if (repetitions === 0) intervalDays = 1;
    else if (repetitions === 1) intervalDays = 6;
    else intervalDays = Math.round(prev.intervalDays * easeFactor);
    repetitions += 1;
  } else {
    repetitions = 0;
    intervalDays = 1;
  }

  easeFactor = easeFactor + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02));
  easeFactor = Math.max(MIN_EASE_FACTOR, easeFactor);

  const nextReviewAt = nowMs + intervalDays * 24 * 60 * 60 * 1000;
  return { easeFactor, intervalDays, repetitions, nextReviewAt };
}
