// First-run guide state. Device-local (localStorage) on purpose: it's a UI
// walkthrough, not account data — a returning user on a new device seeing it
// once more is harmless, and it must be readable synchronously before any
// Supabase round-trip so the guide can gate the very first render.
const KEY = "sanad.onboarded";

/** True once the user has finished (or skipped) the first-run guide. Defaults
 * to TRUE on any storage error so a broken localStorage never traps someone
 * in an onboarding loop. */
export function hasOnboarded(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return true;
  }
}

export function markOnboarded(): void {
  try {
    localStorage.setItem(KEY, "1");
  } catch {
    /* ignore */
  }
}

/** Clear the flag so the guide shows again — wired to Settings' "Replay the
 * app guide". */
export function resetOnboarding(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
