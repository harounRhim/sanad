import { supabase, isSupabaseConfigured } from "./supabase";

// Hard cap per page load — an error thrown inside a render/effect loop would
// otherwise flood the table (and the network) with thousands of identical
// rows before the user even reaches for reload.
const MAX_REPORTS_PER_SESSION = 5;
let reported = 0;
const seen = new Set<string>();

/** Best-effort crash telemetry into the `client_errors` table (schema.sql).
 * Everything here is deliberately swallow-all: error reporting must never
 * become a second error. No-ops when Supabase isn't configured, when signed
 * out (RLS is authenticated-insert-only — the app is auth-gated anyway), on
 * duplicate messages, and past the per-session cap. */
export async function reportClientError(
  message: string,
  stack?: string | null,
  context?: string
): Promise<void> {
  try {
    if (!isSupabaseConfigured) return;
    if (reported >= MAX_REPORTS_PER_SESSION) return;
    const key = message.slice(0, 200);
    if (seen.has(key)) return;
    seen.add(key);
    reported += 1;

    const { data } = await supabase.auth.getSession();
    const userId = data.session?.user.id;
    if (!userId) return;

    await supabase.from("client_errors").insert({
      user_id: userId,
      message: message.slice(0, 2000),
      stack: stack?.slice(0, 8000) ?? null,
      context: context ?? null,
      url: window.location.pathname,
      user_agent: navigator.userAgent.slice(0, 300),
    });
  } catch {
    // Never let telemetry throw.
  }
}

/** Wire the global catch-alls once from main.tsx. */
export function installGlobalErrorReporting(): void {
  window.addEventListener("error", (e) => {
    reportClientError(e.message ?? "window.onerror", e.error?.stack, "window.error");
  });
  window.addEventListener("unhandledrejection", (e) => {
    const reason = e.reason;
    reportClientError(
      reason instanceof Error ? reason.message : String(reason),
      reason instanceof Error ? reason.stack : null,
      "unhandledrejection"
    );
  });
}
