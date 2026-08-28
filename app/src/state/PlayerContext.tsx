import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { AyahAudio } from "../lib/types";
import { audioUrl } from "../lib/audio";
import { useSettings } from "./SettingsContext";

interface PlayerState {
  queue: AyahAudio[];
  index: number;
  isPlaying: boolean;
  rate: number;
  current: AyahAudio | null;
  /** Set when the current track fails to load/play (e.g. the local audio
   * server isn't running, or the URL 404s) — cleared on the next play()
   * attempt. Previously these failures were swallowed silently, which read
   * as "nothing happens" with no way to tell a config problem from a
   * missing recording. */
  error: string | null;
  play: (queue: AyahAudio[], index: number) => void;
  toggle: () => void;
  next: () => void;
  prev: () => void;
  setRate: (r: number) => void;
  stop: () => void;
}

const Ctx = createContext<PlayerState | null>(null);

export function PlayerProvider({ children }: { children: ReactNode }) {
  const { autoplay } = useSettings();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [queue, setQueue] = useState<AyahAudio[]>([]);
  const [index, setIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [rate, setRateState] = useState(1);
  const [error, setError] = useState<string | null>(null);

  if (!audioRef.current && typeof Audio !== "undefined") {
    audioRef.current = new Audio();
  }

  const current = queue[index] ?? null;

  const loadAndPlay = useCallback((track: AyahAudio | undefined) => {
    const el = audioRef.current;
    if (!el || !track) return;
    const url = audioUrl(track.audio_path);
    if (!url) {
      setError("Audio isn't configured (VITE_AUDIO_BASE_URL is unset).");
      return;
    }
    setError(null);
    el.src = url;
    el.playbackRate = rate;
    void el.play().then(() => setIsPlaying(true)).catch(() => {
      setIsPlaying(false);
      setError("Couldn't play this recitation — check the audio server is running.");
    });
  }, [rate]);

  const play = useCallback((q: AyahAudio[], i: number) => {
    setQueue(q);
    setIndex(i);
    loadAndPlay(q[i]);
  }, [loadAndPlay]);

  const next = useCallback(() => {
    setIndex((i) => {
      const ni = i + 1;
      if (ni < queue.length) {
        loadAndPlay(queue[ni]);
        return ni;
      }
      return i;
    });
  }, [queue, loadAndPlay]);

  const prev = useCallback(() => {
    setIndex((i) => {
      const pi = Math.max(0, i - 1);
      loadAndPlay(queue[pi]);
      return pi;
    });
  }, [queue, loadAndPlay]);

  const toggle = useCallback(() => {
    const el = audioRef.current;
    if (!el || !current) return;
    if (el.paused) {
      void el.play();
      setIsPlaying(true);
    } else {
      el.pause();
      setIsPlaying(false);
    }
  }, [current]);

  const stop = useCallback(() => {
    const el = audioRef.current;
    if (el) {
      el.pause();
      el.removeAttribute("src");
    }
    setQueue([]);
    setIndex(0);
    setIsPlaying(false);
  }, []);

  const setRate = useCallback((r: number) => {
    setRateState(r);
    if (audioRef.current) audioRef.current.playbackRate = r;
  }, []);

  // Wire up <audio> events (ended -> autoplay next; play/pause -> state sync;
  // error -> surface it, since a bad/unreachable src doesn't always reject
  // the play() promise the same way across browsers — this is the more
  // reliable signal for "the file didn't actually load").
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const onEnded = () => {
      if (autoplay) next();
      else setIsPlaying(false);
    };
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    const onError = () => {
      setIsPlaying(false);
      setError("Couldn't load this recitation — check the audio server is running.");
    };
    el.addEventListener("ended", onEnded);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("error", onError);
    return () => {
      el.removeEventListener("ended", onEnded);
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("error", onError);
    };
  }, [autoplay, next]);

  const value = useMemo<PlayerState>(
    () => ({ queue, index, isPlaying, rate, current, error, play, toggle, next, prev, setRate, stop }),
    [queue, index, isPlaying, rate, current, error, play, toggle, next, prev, setRate, stop]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePlayer(): PlayerState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("usePlayer must be used within PlayerProvider");
  return ctx;
}
