import { useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "../lib/supabase";
import { useAuth } from "../state/AuthContext";
import type { StreakState } from "../lib/types";

/** Interface spec §06 — 1 joker earned per completed streak length below, capped. */
const JOKER_EARN_EVERY = 7;
const JOKER_CAP = 2;

const EMPTY: StreakState = { current: 0, longest: 0, lastActiveDate: null, jokers: 0, history: {} };

interface Row {
  current: number;
  longest: number;
  last_active_date: string | null;
  jokers: number;
  history: Record<string, "done" | "joker">;
}

function fromRow(r: Row | null): StreakState {
  if (!r) return EMPTY;
  return {
    current: r.current,
    longest: r.longest,
    lastActiveDate: r.last_active_date,
    jokers: r.jokers,
    history: r.history ?? {},
  };
}

function toRow(userId: string, s: StreakState) {
  return {
    user_id: userId,
    current: s.current,
    longest: s.longest,
    last_active_date: s.lastActiveDate,
    jokers: s.jokers,
    history: s.history,
  };
}

function todayStr(d = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function addDays(dateStr: string, n: number): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + n);
  return todayStr(dt);
}

function daysBetween(a: string, b: string): number {
  const [ay, am, ad] = a.split("-").map(Number);
  const [by, bm, bd] = b.split("-").map(Number);
  const da = new Date(ay, am - 1, ad).getTime();
  const db = new Date(by, bm - 1, bd).getTime();
  return Math.round((db - da) / 86400000);
}

function nextState(s: StreakState): StreakState | null {
  const today = todayStr();
  if (s.lastActiveDate === today) return null;

  let current: number;
  let jokers = s.jokers;
  const history = { ...s.history };

  if (s.lastActiveDate == null) {
    current = 1;
  } else {
    const gap = daysBetween(s.lastActiveDate, today);
    if (gap === 1) {
      current = s.current + 1;
    } else if (gap === 2 && jokers > 0) {
      jokers -= 1;
      history[addDays(s.lastActiveDate, 1)] = "joker";
      current = s.current + 1;
    } else {
      current = 1;
    }
  }

  history[today] = "done";
  if (current > 0 && current % JOKER_EARN_EVERY === 0 && jokers < JOKER_CAP) {
    jokers += 1;
  }

  return { current, longest: Math.max(s.longest, current), lastActiveDate: today, jokers, history };
}

/** Server-side streak + joker (PHASE 6 follow-up #8) — 1 row per user in
 * `user_streak`, scoped by RLS to auth.uid(). Local-date based (not epoch ms)
 * since a streak is inherently about calendar days, not 24h windows. */
export function useStreak() {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const queryClient = useQueryClient();
  const queryKey = ["streak", userId];

  const query = useQuery({
    queryKey,
    enabled: Boolean(userId),
    queryFn: async (): Promise<StreakState> => {
      const { data, error } = await supabase
        .from("user_streak")
        .select("current,longest,last_active_date,jokers,history")
        .eq("user_id", userId)
        .maybeSingle();
      if (error) throw error;
      return fromRow(data as Row | null);
    },
  });

  const state = query.data ?? EMPTY;

  /** Call once per real recitation/review completion (e.g. from Practice's
   * surahComplete, Review's a pass, or Listen & Repeat clearing a stage).
   * No-ops if already recorded today. A single missed day is automatically
   * bridged with a joker if one is available — §06 describes this as an
   * offered choice ("Use a joker?"); this hook applies that same rule the
   * next time the app opens rather than via a live notification, which is a
   * larger, separate feature. A gap of 2+ days, or 1 day with no joker
   * available, resets the streak. Every JOKER_EARN_EVERY-day streak earns a
   * joker, up to JOKER_CAP. */
  const recordActivity = useCallback(() => {
    if (!userId) return;
    // Read the LIVE cache, not this render's closure — recordActivity often
    // fires from async grading callbacks/timers whose capturing render is
    // stale by the time they run (same discipline as useMemorization).
    const cur = queryClient.getQueryData<StreakState>(["streak", userId]) ?? EMPTY;
    const next = nextState(cur);
    if (!next) return;

    queryClient.setQueryData<StreakState>(["streak", userId], next);

    supabase
      .from("user_streak")
      .upsert(toRow(userId, next), { onConflict: "user_id" })
      .then(({ error }) => {
        if (error) {
          // eslint-disable-next-line no-console
          console.error("[Sanad] Failed to sync streak:", error.message);
        }
      });
  }, [userId, queryClient]);

  /** Last 7 days (oldest first, ending today) for the week strip (§04.7). */
  const week = useMemo(() => {
    const today = todayStr();
    const days: { date: string; state: "done" | "joker" | "today" | "missed" }[] = [];
    for (let i = 6; i >= 0; i--) {
      const date = addDays(today, -i);
      if (date === today) {
        days.push({ date, state: "today" });
      } else {
        days.push({ date, state: state.history[date] ?? "missed" });
      }
    }
    return days;
  }, [state.history]);

  return { ...state, jokerCap: JOKER_CAP, week, recordActivity, loading: query.isLoading };
}
