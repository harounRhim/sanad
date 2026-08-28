import { useCallback, useEffect, useRef, useState } from "react";
import {
  stepPauseDetector,
  initialPauseState,
  DEFAULT_PAUSE_CONFIG,
  type PauseDetectorState,
} from "../lib/pauseDetector";

/**
 * Continuous-recitation recorder: ONE microphone stream stays open for the
 * whole practice session (no per-āyah "press record" round trip). A silence
 * gap between āyahs (see lib/pauseDetector.ts) triggers `onSegment(blob)`
 * with just-that-āyah's audio, then listening continues immediately with no
 * gap — the caller grades the segment and decides whether to advance (see
 * Practice.tsx), while recording never stops.
 *
 * Implementation trick: rather than manually slicing raw PCM at arbitrary
 * timestamps (which MediaRecorder's chunked webm/opus output doesn't support
 * — only the FIRST chunk carries the container header, so concatenating a
 * later subset alone won't decode), each detected boundary STOPS the current
 * MediaRecorder (yielding one complete, independently-valid blob) and
 * IMMEDIATELY starts a NEW one on the SAME underlying MediaStream. The user
 * never notices a gap and never re-grants microphone permission.
 */
export function useAutoRecorder(onSegment: (blob: Blob) => void) {
  const [listening, setListening] = useState(false);
  const [volume, setVolume] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const dataArrRef = useRef<Float32Array<ArrayBuffer> | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const rafRef = useRef<number | null>(null);
  const cuttingRef = useRef(false);
  const detectorRef = useRef<PauseDetectorState>(initialPauseState(0));

  // Reassigned on every render (not in an effect) so the RAF loop's async
  // MediaRecorder.onstop callback — which can fire well after the render
  // that created it — always calls the CURRENT onSegment closure, never a
  // stale one. This is what lets Practice.tsx reference the current āyah
  // directly instead of threading extra refs through this hook.
  const onSegmentRef = useRef(onSegment);
  onSegmentRef.current = onSegment;

  const startSegmentRecorder = useCallback(() => {
    const stream = streamRef.current;
    if (!stream) return;
    chunksRef.current = [];
    const mr = new MediaRecorder(stream);
    mr.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    mr.start();
    recorderRef.current = mr;
    detectorRef.current = initialPauseState(performance.now());
  }, []);

  const cutSegment = useCallback(() => {
    const mr = recorderRef.current;
    if (!mr || mr.state !== "recording" || cuttingRef.current) return;
    cuttingRef.current = true;
    mr.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: mr.mimeType || "audio/webm" });
      startSegmentRecorder();          // keep listening with ~zero gap
      cuttingRef.current = false;
      onSegmentRef.current(blob);      // grading happens "in the background"
    };
    mr.stop();
  }, [startSegmentRecorder]);

  const loop = useCallback(() => {
    const analyser = analyserRef.current;
    const data = dataArrRef.current;
    if (analyser && data) {
      analyser.getFloatTimeDomainData(data);
      let sumSq = 0;
      for (let i = 0; i < data.length; i++) sumSq += data[i] * data[i];
      const rms = Math.sqrt(sumSq / data.length);
      setVolume(rms);
      if (!cuttingRef.current) {
        const { state, cut } = stepPauseDetector(
          detectorRef.current, rms, performance.now(), DEFAULT_PAUSE_CONFIG
        );
        detectorRef.current = state;
        if (cut) cutSegment();
      }
    }
    rafRef.current = requestAnimationFrame(loop);
  }, [cutSegment]);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const AudioCtx: typeof AudioContext =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new AudioCtx();
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 2048;
      src.connect(analyser);
      audioCtxRef.current = ctx;
      analyserRef.current = analyser;
      dataArrRef.current = new Float32Array(analyser.fftSize);
      startSegmentRecorder();
      setListening(true);
      rafRef.current = requestAnimationFrame(loop);
    } catch (e) {
      setError(
        e instanceof DOMException && e.name === "NotAllowedError"
          ? "Microphone access denied. Allow it in your browser and retry."
          : "Could not start listening."
      );
    }
  }, [loop, startSegmentRecorder]);

  const stop = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    const mr = recorderRef.current;
    if (mr && mr.state === "recording") {
      mr.onstop = null;      // discard the trailing partial segment, don't grade it
      mr.stop();
    }
    recorderRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    audioCtxRef.current?.close();
    audioCtxRef.current = null;
    setListening(false);
    setVolume(0);
  }, []);

  useEffect(() => () => stop(), [stop]);   // always release the mic on unmount

  return { listening, volume, error, start, stop };
}
