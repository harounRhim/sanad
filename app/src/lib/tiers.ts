/**
 * Journey Map / Sūrah Detail (interface spec §04-§06) — derives sūrah-level
 * progression straight from data that already exists (useMemorization's
 * per-āyah SM-2 entries, the `pages` table), no new grading logic. This is
 * deliberately "mostly a UI and labeling problem, not a new backend" per the
 * spec's own §05 framing.
 */
import type { MemorizationEntry, MemorizationStatus, Page } from "./types";

export type SurahTier = "not_started" | "active" | "retained";

function entriesForSurah(surah: number, entries: MemorizationEntry[]): MemorizationEntry[] {
  return entries.filter((e) => e.surah === surah);
}

// Per-āyah credit toward the memorization ring, by SM-2 status. GRADED (not
// all-or-nothing on "mastered") so the ring moves the moment a learner
// recites an āyah correctly in EITHER flow (Recite-now / Listen & Repeat) —
// both feed useMemorization.recordReview, which lands a first correct pass at
// "learning". The old "mastered-only" ratio stayed flat at 0% until an āyah
// survived ~7 reviews, so a full correct recitation looked like it did
// nothing — reported as "the percentage doesn't work." A fully mastered
// sūrah still reads exactly 100% (mastered = 1.0), so `isRetained` (all
// mastered) and this ratio agree at the top end.
const STATUS_WEIGHT: Record<MemorizationStatus, number> = {
  learning: 0.34,
  reviewing: 0.67,
  mastered: 1,
};

/** Sūrah Detail's memorization ring (§04.2): graded fraction of this sūrah
 * memorized, summing each tracked āyah's status weight over the āyah count.
 * Reflects real progress from both the Recite-now and Listen & Repeat flows. */
export function memorizedRatio(surah: number, ayahCount: number, entries: MemorizationEntry[]): number {
  if (ayahCount <= 0) return 0;
  const credit = entriesForSurah(surah, entries).reduce(
    (sum, e) => sum + (STATUS_WEIGHT[e.status] ?? 0),
    0
  );
  return Math.min(1, credit / ayahCount);
}

/** §06's Tier 3 "Retained" bar for freeing an active-slate slot: every āyah
 * of the sūrah has reached "mastered" (streak >= MASTERED_STREAK in
 * useMemorization, which already requires surviving several SM-2 reviews,
 * not just one correct take). */
export function isRetained(surah: number, ayahCount: number, entries: MemorizationEntry[]): boolean {
  if (ayahCount <= 0) return false;
  const bySurah = new Map(entriesForSurah(surah, entries).map((e) => [e.ayah, e]));
  for (let a = 1; a <= ayahCount; a++) {
    const e = bySurah.get(a);
    if (!e || e.status !== "mastered") return false;
  }
  return true;
}

/** Rough §05 tier for map/detail display. "not_started" = zero tracked
 * āyahs; "retained" = every āyah mastered; "active" = anything in between
 * (mirrors §05 Tiers 1-2, which this app doesn't yet distinguish per-āyah). */
export function surahTier(surah: number, ayahCount: number, entries: MemorizationEntry[]): SurahTier {
  if (entriesForSurah(surah, entries).length === 0) return "not_started";
  if (isRetained(surah, ayahCount, entries)) return "retained";
  return "active";
}

/** Number of mushaf pages (of 604) a sūrah's āyahs fall across. A page can
 * span more than one sūrah, so this counts every `pages` row whose range
 * overlaps the sūrah's full āyah span at all, not just an exact match. */
export function pagesForSurah(surah: number, ayahCount: number, pages: Page[]): number {
  return pages.filter((p) => rangeOverlaps(p, surah, 1, surah, ayahCount)).length;
}

function rangeOverlaps(
  p: Page,
  aStartSurah: number,
  aStartAyah: number,
  aEndSurah: number,
  aEndAyah: number
): boolean {
  const beforeStart = p.end_surah < aStartSurah || (p.end_surah === aStartSurah && p.end_ayah < aStartAyah);
  const afterEnd = p.start_surah > aEndSurah || (p.start_surah === aEndSurah && p.start_ayah > aEndAyah);
  return !beforeStart && !afterEnd;
}
