import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "../lib/supabase";
import { useAuth } from "../state/AuthContext";
import type { ActiveSlateState } from "../lib/types";

/** Interface spec §06 — at most this many sūrahs actively in progress at once. */
export const SLATE_CAP = 6;
/** §06 — a stepped-back slot needs this long before a new sūrah can claim it. */
export const COOLDOWN_MS = 72 * 60 * 60 * 1000;

const EMPTY: ActiveSlateState = { active: [], cooldowns: [] };

interface Row {
  active: ActiveSlateState["active"];
  cooldowns: ActiveSlateState["cooldowns"];
}

function fromRow(r: Row | null): ActiveSlateState {
  if (!r) return EMPTY;
  const now = Date.now();
  // Drop long-expired cooldowns on read — storage hygiene only, the
  // render-time filter below already treats them as not-pending either way.
  const cooldowns = (r.cooldowns ?? []).filter((c) => now < c.freedAt + COOLDOWN_MS);
  return { active: r.active ?? [], cooldowns };
}

function toRow(userId: string, s: ActiveSlateState) {
  return { user_id: userId, active: s.active, cooldowns: s.cooldowns };
}

/** Interface spec §06 — the active memorization slate. Tracks which sūrahs
 * currently occupy one of the SLATE_CAP concurrent slots and any in-flight
 * 72h cooldowns from stepping back early. Deliberately knows nothing about
 * *why* a sūrah is retained (no useMemorization import) — callers that also
 * hold memorization data drive releases via `pruneRetained`/`releaseRetained`,
 * keeping this hook a plain slot ledger.
 *
 * Server-side (PHASE 6 follow-up #8) — 1 row per user in `user_active_slate`,
 * scoped by RLS to auth.uid(). Every mutator below updates the React Query
 * cache SYNCHRONOUSLY at the point of mutation (same discipline the old
 * localStorage version used) before firing the Supabase upsert in the
 * background — a caller that mutates and then immediately navigates away
 * (e.g. Sūrah Detail's "Recite now": claim a slot, then route to Practice)
 * must see the effect on return without waiting on a network round trip. */
export function useActiveSlate() {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const queryClient = useQueryClient();
  const queryKey = ["activeSlate", userId];

  const query = useQuery({
    queryKey,
    enabled: Boolean(userId),
    queryFn: async (): Promise<ActiveSlateState> => {
      const { data, error } = await supabase
        .from("user_active_slate")
        .select("active,cooldowns")
        .eq("user_id", userId)
        .maybeSingle();
      if (error) throw error;
      return fromRow(data as Row | null);
    },
  });

  const state = query.data ?? EMPTY;

  /** Live-cache read for the mutators below — they fire from event handlers
   * and effects whose capturing render may be stale (same discipline as
   * useMemorization/useStreak: never compound an update onto closure state). */
  const readCache = useCallback(
    (): ActiveSlateState =>
      queryClient.getQueryData<ActiveSlateState>(["activeSlate", userId]) ?? EMPTY,
    [userId, queryClient]
  );

  const persist = useCallback(
    (next: ActiveSlateState): ActiveSlateState => {
      queryClient.setQueryData<ActiveSlateState>(["activeSlate", userId], next);
      if (userId) {
        supabase
          .from("user_active_slate")
          .upsert(toRow(userId, next), { onConflict: "user_id" })
          .then(({ error }) => {
            if (error) {
              // eslint-disable-next-line no-console
              console.error("[Sanad] Failed to sync active slate:", error.message);
            }
          });
      }
      return next;
    },
    [userId, queryClient]
  );

  const now = Date.now();
  const pendingCooldowns = state.cooldowns.filter((c) => now < c.freedAt + COOLDOWN_MS);
  const slotsOpen = Math.max(0, SLATE_CAP - state.active.length - pendingCooldowns.length);

  const isActive = useCallback(
    (surah: number) => state.active.some((e) => e.surah === surah),
    [state.active]
  );

  /** Earliest moment (epoch ms) a currently-cooling slot becomes usable, or
   * null if none is cooling down. Drives the "Opens in ~Nh" node badge. */
  const nextSlotOpensAt =
    pendingCooldowns.length > 0
      ? Math.min(...pendingCooldowns.map((c) => c.freedAt + COOLDOWN_MS))
      : null;

  /** Genuinely started this sūrah (Listen & Repeat, or a real "Recite now"
   * attempt — §08 Q8 flags exactly what counts as "genuine"). No-ops if
   * already active; refuses (returns false) if the slate is full. Persists
   * and returns synchronously so a caller can safely navigate right after. */
  const claimSlot = useCallback(
    (surah: number): boolean => {
      if (!userId) return false;
      const cur = readCache();
      if (cur.active.some((e) => e.surah === surah)) return true;
      const pending = cur.cooldowns.filter((c) => Date.now() < c.freedAt + COOLDOWN_MS).length;
      if (cur.active.length + pending >= SLATE_CAP) return false;
      persist({
        ...cur,
        active: [...cur.active, { surah, startedAt: Date.now() }],
      });
      return true;
    },
    [userId, readCache, persist]
  );

  /** §06 "Stepping back" — voluntarily frees a slot before Retained, behind
   * a 72h cooldown before a new sūrah can claim it. Progress itself lives in
   * useMemorization and is untouched; this only changes slate membership. */
  const stepBack = useCallback(
    (surah: number) => {
      const cur = readCache();
      persist({
        active: cur.active.filter((e) => e.surah !== surah),
        cooldowns: [...cur.cooldowns, { freedAt: Date.now() }],
      });
    },
    [readCache, persist]
  );

  /** Instant release with no cooldown — §06: reaching Retained frees a slot
   * immediately. No-op if the sūrah isn't currently active. */
  const releaseRetained = useCallback(
    (surah: number) => {
      const cur = readCache();
      if (!cur.active.some((e) => e.surah === surah)) return;
      persist({ ...cur, active: cur.active.filter((e) => e.surah !== surah) });
    },
    [readCache, persist]
  );

  /** Sweeps the active list against a caller-supplied "is this sūrah
   * retained now" check (lib/tiers.ts's isRetained) and releases any that
   * qualify — call once from a screen that also holds memorization data
   * whenever that data changes, so the slate stays honest automatically. */
  const pruneRetained = useCallback(
    (isSurahRetained: (surah: number) => boolean) => {
      const cur = readCache();
      const stillActive = cur.active.filter((e) => !isSurahRetained(e.surah));
      if (stillActive.length === cur.active.length) return;
      persist({ ...cur, active: stillActive });
    },
    [readCache, persist]
  );

  return {
    active: state.active,
    isActive,
    slotsOpen,
    slotsUsed: state.active.length,
    cap: SLATE_CAP,
    nextSlotOpensAt,
    claimSlot,
    stepBack,
    releaseRetained,
    pruneRetained,
    loading: query.isLoading,
  };
}
