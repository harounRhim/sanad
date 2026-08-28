import { useCallback, useEffect, useRef, useState } from "react";
import { pcmFloat32ToWav16kMono } from "../lib/wav";

/**
 * Continuous-recitation recorder, SLIDING-WINDOW variant (2026-07-08).
 *
 * `useAutoRecorder` cuts on silence/max-duration, so there's always a
 * "record a whole chunk, THEN grade it" gap of several seconds before
 * anything colors — reported by the user as "not coloring live". The real
 * bound here is the wav2vec2-large model's CPU decode latency (~1.5-2.5s per
 * clip, measured) — no architecture change makes it instant. What DOES help:
 * grade a short TRAILING window of audio on a fixed timer instead of waiting
 * for a pause or a 4s cap, so results update every ~1.7s instead of every
 * ~4-8s, and each update reflects what was JUST said rather than a whole
 * completed chunk.
 *
 * This needs raw PCM, not MediaRecorder's encoded chunks — a sliding window
 * has to start at an arbitrary sample, and only the FIRST chunk of a
 * MediaRecorder stream carries the container header (same constraint
 * documented in useAutoRecorder). So capture goes through a ScriptProcessorNode
 * (deprecated but simple and universally supported — an AudioWorklet would
 * need its own module file for no real benefit at this scale) into a ring
 * buffer of Float32 samples, and each tick slices the last WINDOW_MS out of
 * it directly.
 */

const WINDOW_MS = 3200;     // trailing audio graded on each tick
const INTERVAL_MS = 1700;   // how often we grade -- close to the model's own
                             // per-clip latency so calls don't queue up faster
                             // than the CPU can actually finish them
const SILENCE_RMS = 0.01;   // skip grading a window that's pure silence

export function useRollingRecorder(onWindow: (blob: Blob) => void) {
  const [listening, setListening] = useState(false);
  const [volume, setVolume] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const silentGainRef = useRef<GainNode | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const sampleCountRef = useRef(0);
  const windowSamplesRef = useRef(0); // WINDOW_MS worth of samples at the context's own rate
  const intervalRef = useRef<number | null>(null);
  const gradingRef = useRef(false);

  // Reassigned every render so the interval's async tick always calls the
  // CURRENT onWindow closure, same pattern as useAutoRecorder.
  const onWindowRef = useRef(onWindow);
  onWindowRef.current = onWindow;

  // `force=true` (only from `stop()`) bypasses the "wait for half a window"
  // minimum — without it, the very last few words of a completed
  // recitation could go permanently ungraded: grading only ever fires on
  // the fixed INTERVAL_MS timer, so stopping right after finishing (the
  // normal thing to do) can beat the next tick to the buffer, found
  // 2026-07-08 ("I recited all the surah, even the last word in black").
  const gradeNow = useCallback((force: boolean) => {
    if (gradingRef.current) return; // previous grading call still in flight -- skip, don't pile up concurrent decodes
    const ctx = ctxRef.current;
    const wanted = windowSamplesRef.current;
    if (!ctx || !wanted) return;
    if (!force && sampleCountRef.current < wanted / 2) return; // not enough audio yet for a useful window

    const chunks = chunksRef.current;
    let need = wanted;
    const picked: Float32Array[] = [];
    for (let i = chunks.length - 1; i >= 0 && need > 0; i--) {
      picked.unshift(chunks[i]);
      need -= chunks[i].length;
    }
    const total = picked.reduce((n, c) => n + c.length, 0);
    if (total === 0) return;
    const merged = new Float32Array(total);
    let off = 0;
    for (const c of picked) {
      merged.set(c, off);
      off += c.length;
    }
    const windowSamples = total > wanted ? merged.subarray(total - wanted) : merged;

    let sumSq = 0;
    for (let i = 0; i < windowSamples.length; i++) sumSq += windowSamples[i] * windowSamples[i];
    if (Math.sqrt(sumSq / windowSamples.length) < SILENCE_RMS) return; // pure silence -- skip a wasted decode call

    const sampleRate = ctx.sampleRate; // captured now -- stop() closes ctx right after calling this
    gradingRef.current = true;
    void pcmFloat32ToWav16kMono(windowSamples, sampleRate)
      .then((wav) => onWindowRef.current(wav))
      .finally(() => {
        gradingRef.current = false;
      });
  }, []);

  const tick = useCallback(() => gradeNow(false), [gradeNow]);

  const stop = useCallback(() => {
    gradeNow(true); // last chance to grade whatever's still in the buffer before it's gone
    if (intervalRef.current != null) window.clearInterval(intervalRef.current);
    intervalRef.current = null;
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    silentGainRef.current?.disconnect();
    void ctxRef.current?.close();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    processorRef.current = null;
    sourceRef.current = null;
    silentGainRef.current = null;
    ctxRef.current = null;
    streamRef.current = null;
    chunksRef.current = [];
    sampleCountRef.current = 0;
    setListening(false);
    setVolume(0);
  }, [gradeNow]);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const AudioCtx: typeof AudioContext =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new AudioCtx();
      ctxRef.current = ctx;
      windowSamplesRef.current = Math.ceil((ctx.sampleRate * WINDOW_MS) / 1000);

      const source = ctx.createMediaStreamSource(stream);
      sourceRef.current = source;
      const processor = ctx.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;
      // ScriptProcessorNode must be connected to a destination to fire at
      // all in some browsers -- route through a silent gain so the mic
      // input never gets played back out loud.
      const silentGain = ctx.createGain();
      silentGain.gain.value = 0;
      silentGainRef.current = silentGain;

      processor.onaudioprocess = (e) => {
        const data = e.inputBuffer.getChannelData(0);
        const copy = new Float32Array(data); // the browser reuses this buffer, must copy
        chunksRef.current.push(copy);
        sampleCountRef.current += copy.length;

        let sumSq = 0;
        for (let i = 0; i < copy.length; i++) sumSq += copy[i] * copy[i];
        setVolume(Math.sqrt(sumSq / copy.length));

        // Bound memory -- keep roughly 2 windows' worth, no need for more.
        const cap = windowSamplesRef.current * 2;
        while (sampleCountRef.current > cap && chunksRef.current.length > 1) {
          sampleCountRef.current -= chunksRef.current[0].length;
          chunksRef.current.shift();
        }
      };

      source.connect(processor);
      processor.connect(silentGain);
      silentGain.connect(ctx.destination);

      setListening(true);
      intervalRef.current = window.setInterval(tick, INTERVAL_MS);
    } catch (e) {
      setError(
        e instanceof DOMException && e.name === "NotAllowedError"
          ? "Microphone access denied. Allow it in your browser and retry."
          : "Could not start listening."
      );
    }
  }, [tick]);

  useEffect(() => () => stop(), [stop]); // always release the mic on unmount

  return { listening, volume, error, start, stop };
}
