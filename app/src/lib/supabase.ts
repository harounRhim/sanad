import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

/** True when both env vars are present so the UI can show a clear setup hint. */
export const isSupabaseConfigured = Boolean(url && key);

if (!isSupabaseConfigured) {
  // eslint-disable-next-line no-console
  console.warn(
    "[Sanad] Supabase not configured. Copy .env.example to .env.local and set " +
      "VITE_SUPABASE_URL + VITE_SUPABASE_PUBLISHABLE_KEY."
  );
}

// Falls back to harmless placeholders so the app still boots without a .env.local
// (queries will fail and surface the setup hint instead of crashing on import).
export const supabase = createClient(
  url || "https://placeholder.supabase.co",
  key || "placeholder-anon-key"
);
