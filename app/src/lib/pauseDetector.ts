/**
 * Pure pause/silence detector driving continuous-recitation auto-segmentation
 * (Practice.tsx). Framework-free and side-effect-free on purpose so it can be
 * reasoned about (and probed) independently of the Web Audio/MediaRecorder
 * plumbing that feeds it real RMS samples.
 *
 * Tuning note: SPEECH_RMS/PAUSE_MS/MIN_SEGMENT_MS below are reasonable
 * starting defaults, NOT validated against real microphone/recitation audio
 * (this repo has no way to record real speech in an automated way) — expect
 * to retune them against real usage. See docs/ROADMAP_V2.txt.
 */

export interface PauseDetectorState {
  hasSpeech: boolean;            // has the current segment had any speech yet?
  silenceStartMs: number | null; // when the current unbroken silence run began
  segmentStartMs: number;        // when the current segment started recording
}

export interface PauseDetectorConfig {
  speechRms: number;   // RMS above this counts as "speaking"
  pauseMs: number;     // silence duration that counts as an āyah boundary
  minSegmentMs: number; // never cut a segment shorter than this, even if paused
  maxSegmentMs: number; // force a cut after this long even WITHOUT a pause
}

export const DEFAULT_PAUSE_CONFIG: PauseDetectorConfig = {
  speechRms: 0.02,
  pauseMs: 700,
  minSegmentMs: 1200,
  // Lowered from 8000ms (2026-07-08, real user feedback: "cursor is not
  // passing to the next āyah fast enough") — 8s meant the cursor could only
  // ever catch up that often at best when reciting fluently with no real
  // pauses, on top of grading latency after each cut. Shorter segments both
  // trigger more often AND process faster (CPU alignment cost scales with
  // audio length), improving perceived responsiveness on both fronts.
  maxSegmentMs: 4000,
};

export function initialPauseState(nowMs: number): PauseDetectorState {
  return { hasSpeech: false, silenceStartMs: null, segmentStartMs: nowMs };
}

/**
 * Advance the detector by one sample. Returns the next state and whether
 * THIS sample is the one that should trigger cutting the segment.
 *
 * Never cuts before any speech has been seen (silence at the very start of a
 * segment — e.g. while the reciter takes a breath — doesn't count), and
 * never cuts a segment shorter than `minSegmentMs` even once speech + a long
 * pause have both happened (guards against a stray cough/blip).
 *
 * ALSO force-cuts after `maxSegmentMs` even with NO pause at all (found
 * 2026-07-07: a fluently-recited sūrah with no real gaps between āyahs never
 * triggered a silence-based cut, so the whole recitation piled into one
 * segment that only ever got graded as if it were the first āyah). This is
 * what makes continuous recitation with window-based grading — see
 * evaluate_window server-side — actually receive periodic segments to grade,
 * regardless of how the reciter paces their pauses.
 */
export function stepPauseDetector(
  state: PauseDetectorState,
  rms: number,
  nowMs: number,
  cfg: PauseDetectorConfig = DEFAULT_PAUSE_CONFIG
): { state: PauseDetectorState; cut: boolean } {
  const speaking = rms > cfg.speechRms;
  const segmentDur = nowMs - state.segmentStartMs;

  if (segmentDur >= cfg.maxSegmentMs && (state.hasSpeech || speaking)) {
    return {
      state: { ...state, hasSpeech: true, silenceStartMs: speaking ? null : state.silenceStartMs },
      cut: true,
    };
  }

  if (speaking) {
    return { state: { ...state, hasSpeech: true, silenceStartMs: null }, cut: false };
  }
  if (!state.hasSpeech) {
    return { state, cut: false };
  }

  const silenceStartMs = state.silenceStartMs ?? nowMs;
  const silenceDur = nowMs - silenceStartMs;
  const cut = silenceDur >= cfg.pauseMs && segmentDur >= cfg.minSegmentMs;
  return { state: { ...state, silenceStartMs }, cut };
}
