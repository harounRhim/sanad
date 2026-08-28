const KEY = "sanad.lastRead";

export interface LastRead {
  surah: number;
  ayah: number;
}

export function getLastRead(): LastRead | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as LastRead) : null;
  } catch {
    return null;
  }
}

export function setLastRead(surah: number, ayah: number): void {
  localStorage.setItem(KEY, JSON.stringify({ surah, ayah }));
}
