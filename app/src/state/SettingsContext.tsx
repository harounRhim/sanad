import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { DEFAULT_RECITER } from "../lib/reciters";

export type Theme = "system" | "light" | "dark";
export type ReaderLayout = "list" | "mushaf";

export interface Settings {
  theme: Theme;
  fontScale: number; // 1.0 = base
  defaultReciter: string;
  tajweed: boolean;
  autoplay: boolean;
  layout: ReaderLayout;
}

const DEFAULTS: Settings = {
  theme: "system",
  fontScale: 1,
  defaultReciter: DEFAULT_RECITER,
  tajweed: true,
  autoplay: true,
  layout: "list",
};

const KEY = "sanad.settings";

interface SettingsCtx extends Settings {
  set: <K extends keyof Settings>(key: K, value: Settings[K]) => void;
}

const Ctx = createContext<SettingsCtx | null>(null);

function load(): Settings {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

function applyTheme(theme: Theme) {
  const dark =
    theme === "dark" ||
    (theme === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(load);

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(settings));
    applyTheme(settings.theme);
  }, [settings]);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (settings.theme === "system") applyTheme("system");
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [settings.theme]);

  const value = useMemo<SettingsCtx>(
    () => ({
      ...settings,
      set: (key, val) => setSettings((s) => ({ ...s, [key]: val })),
    }),
    [settings]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSettings(): SettingsCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSettings must be used within SettingsProvider");
  return ctx;
}
