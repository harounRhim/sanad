import { useQuery } from "@tanstack/react-query";
import { supabase } from "../lib/supabase";
import type { Surah, Juz, Page, Verse, Segment, AyahAudio } from "../lib/types";
import { isArabic, normalizeArabic, escapeLike } from "../lib/arabic";

const STALE = 1000 * 60 * 60; // 1h — reference data barely changes
const SEARCH_LIMIT = 50;

export function useSurahs() {
  return useQuery({
    queryKey: ["surahs"],
    staleTime: STALE,
    queryFn: async (): Promise<Surah[]> => {
      const { data, error } = await supabase
        .from("surahs")
        .select("*")
        .order("surah");
      if (error) throw error;
      return data as Surah[];
    },
  });
}

export function useSurah(surah: number) {
  return useQuery({
    queryKey: ["surah", surah],
    staleTime: STALE,
    queryFn: async (): Promise<Surah | null> => {
      const { data, error } = await supabase
        .from("surahs")
        .select("*")
        .eq("surah", surah)
        .maybeSingle();
      if (error) throw error;
      return data as Surah | null;
    },
  });
}

export function useJuz() {
  return useQuery({
    queryKey: ["juz"],
    staleTime: STALE,
    queryFn: async (): Promise<Juz[]> => {
      const { data, error } = await supabase.from("juz").select("*").order("juz");
      if (error) throw error;
      return data as Juz[];
    },
  });
}

export function usePages() {
  return useQuery({
    queryKey: ["pages"],
    staleTime: STALE,
    queryFn: async (): Promise<Page[]> => {
      const { data, error } = await supabase.from("pages").select("*").order("page");
      if (error) throw error;
      return data as Page[];
    },
  });
}

export function useVerses(surah: number) {
  return useQuery({
    queryKey: ["verses", surah],
    staleTime: STALE,
    queryFn: async (): Promise<Verse[]> => {
      const { data, error } = await supabase
        .from("verses")
        .select("*")
        .eq("surah", surah)
        .order("ayah");
      if (error) throw error;
      return data as Verse[];
    },
  });
}

/**
 * All verses within a mushaf PAGE range (inclusive), in reading order. A page
 * can span more than one surah (short surahs near the end of the muṣḥaf), so
 * this can't just be a `.eq("surah", ...)` query like useVerses — it needs an
 * OR of three cases: the tail of the start surah, any surah strictly between,
 * and the head of the end surah (collapsed to one range when start===end).
 */
export function usePageVerses(page: Page | undefined) {
  return useQuery({
    queryKey: ["pageVerses", page?.page],
    enabled: Boolean(page),
    staleTime: STALE,
    queryFn: async (): Promise<Verse[]> => {
      if (!page) return [];
      const { start_surah, start_ayah, end_surah, end_ayah } = page;
      const filter =
        start_surah === end_surah
          ? `and(surah.eq.${start_surah},ayah.gte.${start_ayah},ayah.lte.${end_ayah})`
          : [
              `and(surah.eq.${start_surah},ayah.gte.${start_ayah})`,
              `and(surah.gt.${start_surah},surah.lt.${end_surah})`,
              `and(surah.eq.${end_surah},ayah.lte.${end_ayah})`,
            ].join(",");
      const { data, error } = await supabase
        .from("verses")
        .select("*")
        .or(filter)
        .order("surah")
        .order("ayah");
      if (error) throw error;
      return data as Verse[];
    },
  });
}

export interface DrillExample {
  surah: number;
  ayah: number;
  segment: string;
  text: string;
}

/**
 * Up to 5 short example āyahs containing a given tajweed rule, for the
 * drills screen (Roadmap V2 Phase 3). Reuses the existing `tajweed_segments`
 * + `verses` tables directly — no Python/ML involved, unlike
 * `tajweed.correction.calibrate.select_focus_ayahs` (which does the
 * equivalent pick offline for calibration sampling); a live Supabase query is
 * the right tool here since this needs to answer on demand from the browser.
 * Caps the initial segment scan at 60 rows (rules like ikhfa/ghunnah occur
 * thousands of times in the full text — no need to pull them all just to
 * pick 5 short examples) and ranks the resulting distinct āyahs by verse
 * length so shorter/quicker examples surface first.
 */
export function useDrillExamples(rule: string) {
  return useQuery({
    queryKey: ["drillExamples", rule],
    enabled: Boolean(rule),
    staleTime: STALE,
    queryFn: async (): Promise<DrillExample[]> => {
      const { data: segs, error } = await supabase
        .from("tajweed_segments")
        .select("surah,ayah,segment")
        .eq("rule", rule)
        .limit(60);
      if (error) throw error;

      const bySurahAyah = new Map<string, { surah: number; ayah: number; segment: string }>();
      for (const s of segs ?? []) {
        const key = `${s.surah}:${s.ayah}`;
        if (!bySurahAyah.has(key)) bySurahAyah.set(key, s);
      }
      const pairs = Array.from(bySurahAyah.values()).slice(0, 20);
      if (pairs.length === 0) return [];

      const filter = pairs
        .map((p) => `and(surah.eq.${p.surah},ayah.eq.${p.ayah})`)
        .join(",");
      const { data: verses, error: vErr } = await supabase
        .from("verses")
        .select("surah,ayah,text")
        .or(filter);
      if (vErr) throw vErr;

      const textByKey = new Map((verses ?? []).map((v) => [`${v.surah}:${v.ayah}`, v.text]));
      return pairs
        .map((p) => ({ ...p, text: textByKey.get(`${p.surah}:${p.ayah}`) ?? "" }))
        .filter((p) => p.text)
        .sort((a, b) => a.text.length - b.text.length)
        .slice(0, 5);
    },
  });
}

/**
 * Verses for an arbitrary, non-contiguous list of (surah, ayah) pairs — used
 * by Review.tsx (Roadmap V2 Phase 5) to fetch the text for whatever's due
 * today, which (unlike usePageVerses' page range or useVerses' whole surah)
 * has no natural contiguous range. Results are NOT guaranteed to come back
 * in `pairs` order (Supabase's `.or()` doesn't promise it) — callers that
 * care about a specific order should re-sort by matching pairs themselves.
 */
export function useVersesByPairs(pairs: { surah: number; ayah: number }[]) {
  const key = pairs.map((p) => `${p.surah}:${p.ayah}`).sort().join(",");
  return useQuery({
    queryKey: ["versesByPairs", key],
    enabled: pairs.length > 0,
    staleTime: STALE,
    queryFn: async (): Promise<Verse[]> => {
      const filter = pairs
        .map((p) => `and(surah.eq.${p.surah},ayah.eq.${p.ayah})`)
        .join(",");
      const { data, error } = await supabase.from("verses").select("*").or(filter);
      if (error) throw error;
      return data as Verse[];
    },
  });
}

export function useSegments(surah: number) {
  return useQuery({
    queryKey: ["segments", surah],
    staleTime: STALE,
    queryFn: async (): Promise<Segment[]> => {
      const { data, error } = await supabase
        .from("tajweed_segments")
        .select("*")
        .eq("surah", surah);
      if (error) throw error;
      return data as Segment[];
    },
  });
}

/**
 * Full-text verse search. Arabic queries match the diacritic-insensitive
 * `text_normalized` column; Latin queries match the English `translation` and
 * `transliteration`. Returns matching verses (with translation) for display.
 */
export function useVerseSearch(query: string) {
  const q = query.trim();
  return useQuery({
    queryKey: ["search", q],
    enabled: q.length >= 2,
    staleTime: 1000 * 60 * 5,
    queryFn: async (): Promise<Verse[]> => {
      const sel = "surah, ayah, text, translation, transliteration";
      if (isArabic(q)) {
        const norm = escapeLike(normalizeArabic(q));
        const { data, error } = await supabase
          .from("verses")
          .select(sel)
          .ilike("text_normalized", `%${norm}%`)
          .order("surah")
          .order("ayah")
          .limit(SEARCH_LIMIT);
        if (error) throw error;
        return data as Verse[];
      }
      const term = escapeLike(q);
      const { data, error } = await supabase
        .from("verses")
        .select(sel)
        .or(`translation.ilike.%${term}%,transliteration.ilike.%${term}%`)
        .order("surah")
        .order("ayah")
        .limit(SEARCH_LIMIT);
      if (error) throw error;
      return data as Verse[];
    },
  });
}

export function useAudio(surah: number, reciter: string) {
  return useQuery({
    queryKey: ["audio", surah, reciter],
    staleTime: STALE,
    enabled: Boolean(surah && reciter),
    queryFn: async (): Promise<AyahAudio[]> => {
      const { data, error } = await supabase
        .from("ayah_audio")
        .select("*")
        .eq("surah", surah)
        .eq("reciter", reciter)
        .order("ayah");
      if (error) throw error;
      // Skip rows flagged by audio_verify/audio_correct. Filtered client-side so
      // it works whether or not the `verified` column migration has been applied
      // (missing column => undefined => kept).
      return (data as AyahAudio[]).filter((r) => r.verified !== false);
    },
  });
}
