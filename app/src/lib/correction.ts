/**
 * Client for the Tajweed correction API (server/app.py). The engine runs Python
 * + wav2vec2 on a server (your PC via a tunnel, or a VM); the browser records,
 * encodes WAV (see lib/wav.ts), and POSTs it here for grading.
 */

const API = (import.meta.env.VITE_CORRECTION_API_URL || "").replace(/\/+$/, "");

export const isCorrectionConfigured = Boolean(API);

export interface GradeResult {
  rule: string;
  segment: string;
  start_idx: number;
  end_idx: number;
  expected: string;
  measured: string;
  measured_harakat: number | null;
  nasality: number | null;
  status: "ok" | "warn" | "missing_audio" | string;
  message: string;
}

/** Roadmap V2 Phase 1 — one tajweed rule touching a given word (subset of GradeResult). */
export interface WordRule {
  rule: string;
  status: string;
  message: string;
  measured_harakat: number | null;
}

/** Roadmap V2 Phase 1 — combined content+tajweed verdict for one word of the āyah. */
export interface WordScore {
  word: string;
  start_idx: number;
  end_idx: number;
  content_ok: boolean;
  verdict: "green" | "yellow" | "red";
  rules: WordRule[];
}

export interface GradeReport {
  surah: number;
  ayah: number;
  duration_s: number;
  haraka_unit_s: number | null;
  aligner: string;
  /** Roadmap V2 Phase 0 — content sanity check, independent of the timing grade.
   * "unknown" only for a non-decoding aligner (not expected from the live API). */
  content_status: "ok" | "content_mismatch" | "unknown";
  content_cer: number | null;
  decoded_text: string | null;
  summary: { ok: number; warn: number; total: number };
  results: GradeResult[];
  word_scores: WordScore[];
}

/** A word-level verdict additionally tagged with which āyah it belongs to
 * (null only if it somehow falls outside every āyah span — shouldn't happen,
 * but the server computes it defensively). Shared shape for any endpoint
 * that grades across more than one āyah at a time. */
export interface AyahTaggedWordScore extends WordScore {
  ayah: number | null;
}

/**
 * Roadmap V2 (2026-07-08) — "a sūrah is just a paragraph" report shape. The
 * caller doesn't tell the server which āyah a clip is — the server LOCATES
 * it within the whole sūrah from its content (content_check.locate_best_span)
 * and grades only the identified range. This is what replaced the earlier
 * cursor/window design (WindowReport, confirmed_ayahs/resume_ayah) — that
 * design required the CLIENT to track "where we are" and kept getting stuck
 * when a single confirmation failed; this one is fully stateless per clip,
 * so there's no cursor to get stuck in the first place.
 */
export interface ClipReport {
  surah: number;
  located: boolean;          // false = nothing in the whole sūrah resembled this clip
  ayah_from: number | null;  // null iff !located
  ayah_to: number | null;
  duration_s: number;
  aligner: string;
  content_status: "ok" | "content_mismatch" | "unknown";
  content_cer: number | null;
  decoded_text: string | null;
  word_scores: AyahTaggedWordScore[];
}

export async function correctionHealthy(): Promise<boolean> {
  if (!API) return false;
  try {
    const r = await fetch(`${API}/health`, { method: "GET" });
    if (!r.ok) return false;
    const d = await r.json();
    return Boolean(d.model_loaded);
  } catch {
    return false;
  }
}

export async function gradeRecitation(
  surah: number,
  ayah: number,
  wav: Blob
): Promise<GradeReport> {
  if (!API) {
    throw new Error(
      "Correction API not configured — set VITE_CORRECTION_API_URL in .env.local."
    );
  }
  const fd = new FormData();
  fd.append("surah", String(surah));
  fd.append("ayah", String(ayah));
  fd.append("file", wav, `rec_${surah}_${ayah}.wav`);

  const res = await fetch(`${API}/grade`, { method: "POST", body: fd });
  if (!res.ok) {
    let detail = `Erreur ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return (await res.json()) as GradeReport;
}

/**
 * Grades a clip against a WHOLE sūrah treated as one paragraph — no āyah to
 * specify. The server locates where the clip's content falls within the
 * sūrah and grades just that range (evaluate_clip). This is what makes
 * continuous recitation genuinely stateless: every clip is graded
 * independently, so there's no client-tracked position that can get stuck.
 *
 * `nearAyah` (optional) — a SOFT proximity hint (the caller's last-known
 * position), not a constraint: some short phrases repeat word-for-word
 * elsewhere in the same sūrah (e.g. Al-Fātiḥa's "الرحمن الرحيم" is both the
 * tail of āyah 1 and the whole of āyah 3), and a fully stateless search has
 * no way to prefer the occurrence actually being recited. The server only
 * uses this to break a near-tie between already-comparable matches — it
 * never overrides a clearly better match elsewhere, so this can't reintroduce
 * the old cursor design's "stuck" failure mode.
 */
export async function gradeClip(surah: number, wav: Blob, nearAyah?: number): Promise<ClipReport> {
  if (!API) {
    throw new Error(
      "Correction API not configured — set VITE_CORRECTION_API_URL in .env.local."
    );
  }
  const fd = new FormData();
  fd.append("surah", String(surah));
  fd.append("file", wav, `rec_${surah}.wav`);
  if (nearAyah != null) fd.append("near_ayah", String(nearAyah));

  const res = await fetch(`${API}/grade_clip`, { method: "POST", body: fd });
  if (!res.ok) {
    let detail = `Erreur ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return (await res.json()) as ClipReport;
}
