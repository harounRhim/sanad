/**
 * Audio is hosted on Cloudflare (R2/CDN); the DB stores only relative paths.
 * Prepend the configured base URL at runtime.
 */
export function audioUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path; // already absolute
  const base = (import.meta.env.VITE_AUDIO_BASE_URL || "").replace(/\/+$/, "");
  const rel = path.replace(/^\/+/, "");
  return base ? `${base}/${rel}` : rel;
}

export const isAudioConfigured = Boolean(import.meta.env.VITE_AUDIO_BASE_URL);
