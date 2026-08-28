import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "../lib/supabase";
import { useAuth } from "../state/AuthContext";
import type { MemorizationEntry, MemorizationStatus } from "../lib/types";
import { applySM2, INITIAL_SRS_STATE } from "../lib/srs";

// Streak thresholds driving new->learning->reviewing->mastered. Deliberately
// simple for Phase 4 (a first-order signal of practice history) — Phase 5's
// spaced-repetition scheduler is the more rigorous mechanism, this just needs
// to give a reasonable "where am I" overview and feed it a starting streak.
const REVIEWING_STREAK = 3;
const MASTERED_STREAK = 7;

function statusForStreak(streak: number): MemorizationStatus {
  if (streak >= MASTERED_STREAK) return "mastered";
  if (streak >= REVIEWING_STREAK) return "reviewing";
  return "learning";
}

interface Row {
  surah: number;
  ayah: number;
  status: MemorizationStatus;
  streak: number;
  last_reviewed_at: string | null;
  ease_factor: number;
  interval_days: number;
  repetitions: number;
  next_review_at: string | null;
}

function fromRow(r: Row): MemorizationEntry {
  return {
    surah: r.surah,
    ayah: r.ayah,
    status: r.status,
    streak: r.streak,
    lastReviewedAt: r.last_reviewed_at ? new Date(r.last_reviewed_at).getTime() : 0,
    easeFactor: r.ease_factor,
    intervalDays: r.interval_days,
    repetitions: r.repetitions,
    nextReviewAt: r.next_review_at ? new Date(r.next_review_at).getTime() : 0,
  };
}

function toRow(userId: string, e: MemorizationEntry) {
  return {
    user_id: userId,
    surah: e.surah,
    ayah: e.ayah,
    status: e.status,
    streak: e.streak,
    last_reviewed_at: new Date(e.lastReviewedAt).toISOString(),
    ease_factor: e.easeFactor,
    interval_days: e.intervalDays,
    repetitions: e.repetitions,
    next_review_at: new Date(e.nextReviewAt).toISOString(),
  };
}

/** Server-side memorization progress (PHASE 6 follow-up #8) — one row per
 * (user, surah, ayah) in `user_memorization`, scoped by RLS to auth.uid().
 * Replaces the earlier localStorage-only tracker: progress is now tied to
 * the account, not the browser, which is the whole point of requiring one. */
export function useMemorization() {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const queryClient = useQueryClient();
  const queryKey = ["memorization", userId];

  const query = useQuery({
    queryKey,
    enabled: Boolean(userId),
    queryFn: async (): Promise<MemorizationEntry[]> => {
      const { data, error } = await supabase
        .from("user_memorization")
        .select("surah,ayah,status,streak,last_reviewed_at,ease_factor,interval_days,repetitions,next_review_at")
        .eq("user_id", userId);
      if (error) throw error;
      return (data as Row[]).map(fromRow);
    },
  });

  const entries = query.data ?? [];

  const get = useCallback(
    (surah: number, ayah: number): MemorizationEntry | undefined =>
      entries.find((e) => e.surah === surah && e.ayah === ayah),
    [entries]
  );

  /** Feed a real grading result (Practice.tsx / Review.tsx) into the tracker,
   * as an SM-2 "recall quality" (0-5 — see lib/grading.ts's srsQuality()).
   * quality>=3 counts as a pass for the streak/status overview (Phase 4): it
   * advances the streak (and status once it crosses a threshold); a miss
   * resets the streak but does NOT downgrade a status already reached — one
   * bad take shouldn't erase "reviewing" progress built over many good ones.
   * Separately, ALWAYS runs the SM-2 update (Phase 5) to (re)schedule
   * nextReviewAt, regardless of pass/fail — that's the whole point of SRS.
   *
   * `prev` is looked up INSIDE the setQueryData updater (against the live
   * cache), never from this render's closure — callers fire recordReview in
   * bursts (finishChunk loops over a whole chunk, timers fire after the
   * capturing render is long gone) and a closure lookup would compound each
   * update onto stale state, silently losing streak increments. The updater
   * runs synchronously, so `next` is available immediately after for the
   * background Supabase upsert. */
  const recordReview = useCallback(
    (surah: number, ayah: number, quality: number) => {
      if (!userId) return;
      let next: MemorizationEntry | null = null;

      queryClient.setQueryData<MemorizationEntry[]>(["memorization", userId], (list) => {
        const cur = list ?? [];
        const i = cur.findIndex((e) => e.surah === surah && e.ayah === ayah);
        const prev = i >= 0 ? cur[i] : null;
        const passed = quality >= 3;
        const streak = passed ? (prev?.streak ?? 0) + 1 : 0;
        const status: MemorizationStatus = passed ? statusForStreak(streak) : prev?.status ?? "learning";
        const sm2 = applySM2(prev ?? INITIAL_SRS_STATE, quality, Date.now());
        next = {
          surah, ayah, streak, status, lastReviewedAt: Date.now(),
          easeFactor: sm2.easeFactor, intervalDays: sm2.intervalDays,
          repetitions: sm2.repetitions, nextReviewAt: sm2.nextReviewAt,
        };
        if (i >= 0) {
          const copy = cur.slice();
          copy[i] = next;
          return copy;
        }
        return [...cur, next];
      });

      if (!next) return;
      supabase
        .from("user_memorization")
        .upsert(toRow(userId, next), { onConflict: "user_id,surah,ayah" })
        .then(({ error }) => {
          if (error) {
            // eslint-disable-next-line no-console
            console.error("[Sanad] Failed to sync memorization progress:", error.message);
          }
        });
    },
    [userId, queryClient]
  );

  // `syncBroken` = the initial read itself failed (most likely: schema.sql's
  // user_* tables were never created in this Supabase project). Surfaced as
  // a banner in Layout — without it the app looks fine while silently
  // persisting nothing, which is the worst possible failure mode for a
  // progress tracker.
  return { entries, get, recordReview, loading: query.isLoading, syncBroken: query.isError };
}
