// Row shapes mirror the Supabase schema (see ../../schema.sql).

export interface Surah {
  surah: number;
  name_ar: string;
  name_en: string;
  name_tr: string;
  ayah_count: number;
  revelation_place: "makki" | "madani";
}

export interface Juz {
  juz: number;
  start_surah: number;
  start_ayah: number;
  end_surah: number;
  end_ayah: number;
}

export interface Page {
  page: number;
  start_surah: number;
  start_ayah: number;
  end_surah: number;
  end_ayah: number;
}

export interface Verse {
  surah: number;
  ayah: number;
  text: string;
  text_normalized?: string | null;
  translation?: string | null;
  transliteration?: string | null;
}

export interface Segment {
  surah: number;
  ayah: number;
  rule: string;
  start_idx: number;
  end_idx: number;
  segment: string;
  word: string;
}

export interface AyahAudio {
  surah: number;
  ayah: number;
  reciter: string;
  audio_path: string;
  verified?: boolean; // present once the cleanup migration is applied
  flag_reason?: string | null;
}

export interface Bookmark {
  surah: number;
  ayah: number;
  snippet: string;
  createdAt: number;
}

// Roadmap V2 Phase 4 — memorization (hifz) tracker. Local-only for now (no
// user accounts yet); migrate to a real Supabase table + RLS once auth
// exists, same plan as noted for this in docs/ROADMAP_V2.txt.
export type MemorizationStatus = "learning" | "reviewing" | "mastered";

export interface MemorizationEntry {
  surah: number;
  ayah: number;
  status: MemorizationStatus;
  streak: number;          // consecutive correct recitations, drives status
  lastReviewedAt: number;  // epoch ms
  // Roadmap V2 Phase 5 — SM-2 spaced-repetition schedule (see lib/srs.ts).
  easeFactor: number;
  intervalDays: number;
  repetitions: number;
  nextReviewAt: number;    // epoch ms; due for review once this has passed
}

// Interface spec §06 — the active memorization slate: at most SLATE_CAP
// sūrahs in progress at once (see hooks/useActiveSlate.ts). A slot frees
// automatically once a sūrah reaches the "retained" tier (lib/tiers.ts), or
// manually via stepping back, which starts a 72h cooldown before a new
// sūrah can claim that freed slot.
export interface ActiveSlateEntry {
  surah: number;
  startedAt: number; // epoch ms
}

export interface SlateCooldown {
  freedAt: number; // epoch ms — usable again at freedAt + COOLDOWN_MS
}

export interface ActiveSlateState {
  active: ActiveSlateEntry[];
  cooldowns: SlateCooldown[];
}

// Interface spec §06 — streak + joker.
export interface StreakState {
  current: number;
  longest: number;
  lastActiveDate: string | null; // YYYY-MM-DD, local date of most recent counted activity
  jokers: number;
  history: Record<string, "done" | "joker">; // date -> how that day was covered
}
