import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../state/AuthContext";
import { isSupabaseConfigured } from "../lib/supabase";

type Mode = "signin" | "signup";

// Off by default — Google sign-in needs a Google Cloud OAuth client (blocked
// on the project owner having a credit card to verify Google Cloud) plus
// enabling the provider in the Supabase dashboard, neither of which is done
// yet. The button/logic below is fully wired; set VITE_GOOGLE_AUTH_ENABLED=true
// in .env.local once both are set up — no code changes needed at that point.
const GOOGLE_AUTH_ENABLED = import.meta.env.VITE_GOOGLE_AUTH_ENABLED === "true";

/** Google's OAuth consent screen bounces back to `redirectTo` (this app's
 * origin) with `?error=...&error_description=...` on the query string when
 * something goes wrong (user cancelled, provider misconfigured, etc.) —
 * there's no other channel to learn that here since the whole page
 * navigated away and back. */
function oauthErrorFromUrl(): string | null {
  const params = new URLSearchParams(window.location.search);
  return params.get("error_description") || params.get("error");
}

export default function Login() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [mode, setMode] = useState<Mode>("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(oauthErrorFromUrl);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [googleBusy, setGoogleBusy] = useState(false);

  // Already signed in (bookmark to /login, back-button after auth, the
  // Google OAuth round-trip landing here) — go straight in instead of
  // showing a sign-in form to someone who is signed in.
  useEffect(() => {
    if (!auth.loading && auth.user) navigate(from, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.loading, auth.user]);

  const forgotPassword = async () => {
    setError(null);
    setNotice(null);
    if (!email) {
      setError("Enter your email above first, then tap Forgot password.");
      return;
    }
    const { error } = await auth.resetPassword(email);
    if (error) setError(error);
    else setNotice("Password-reset email sent — check your inbox.");
  };

  const continueWithGoogle = async () => {
    if (googleBusy) return;
    setError(null);
    setGoogleBusy(true);
    const { error } = await auth.signInWithGoogle();
    if (error) {
      setError(error);
      setGoogleBusy(false);
    }
    // On success the browser navigates to Google — nothing left to do here.
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      if (mode === "signin") {
        const { error } = await auth.signIn(email, password);
        if (error) setError(error);
        else navigate(from, { replace: true });
      } else {
        const { error, needsEmailConfirm } = await auth.signUp(email, password, name);
        if (error) setError(error);
        else if (needsEmailConfirm) setNotice("Check your inbox to confirm your email, then sign in.");
        else navigate(from, { replace: true });
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-brand-cream px-5 dark:bg-brand-dark">
      {/* ambient glow */}
      <div className="pointer-events-none absolute -left-24 -top-24 h-72 w-72 rounded-full bg-brand-emerald/15 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-24 -right-16 h-72 w-72 rounded-full bg-brand-gold/20 blur-3xl" />

      <div className="relative w-full max-w-sm">
        <div className="rounded-3xl border border-brand-muted/10 bg-brand-surface/90 p-7 shadow-soft backdrop-blur dark:bg-brand-darkSurface/90">
          <div className="mb-7 text-center">
            <p className="quran text-3xl text-brand-emerald dark:text-brand-emeraldLight">سَنَد</p>
            <h1 className="mt-2 text-lg font-bold text-brand-ink dark:text-brand-darkInk">Sanad</h1>
            <p className="mt-1 text-xs text-brand-muted dark:text-brand-darkMuted">
              {mode === "signin"
                ? "Welcome back — pick up where you left off."
                : "An account is required to track your streak and memorization progress."}
            </p>
          </div>

          {!isSupabaseConfigured && (
            <p className="mb-4 rounded-lg bg-amber-500/10 px-3 py-2 text-center text-xs text-amber-700 dark:text-amber-400">
              Supabase isn't configured yet — set VITE_SUPABASE_URL + VITE_SUPABASE_PUBLISHABLE_KEY in .env.local.
            </p>
          )}

          {GOOGLE_AUTH_ENABLED && (
            <>
              <button
                type="button"
                onClick={continueWithGoogle}
                disabled={googleBusy || !isSupabaseConfigured}
                className="mb-5 flex w-full items-center justify-center gap-2.5 rounded-xl border border-brand-muted/20 bg-white py-2.5 text-sm font-semibold text-brand-ink shadow-soft transition hover:bg-brand-cream disabled:opacity-50"
              >
                <GoogleMark />
                {googleBusy ? "Redirecting…" : "Continue with Google"}
              </button>

              <div className="mb-5 flex items-center gap-3">
                <span className="h-px flex-1 bg-brand-muted/15" />
                <span className="text-[11px] uppercase tracking-wide text-brand-muted dark:text-brand-darkMuted">or</span>
                <span className="h-px flex-1 bg-brand-muted/15" />
              </div>
            </>
          )}

          <div className="mb-5 inline-flex w-full rounded-lg bg-brand-muted/10 p-1">
            {(["signin", "signup"] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => {
                  setMode(m);
                  setError(null);
                  setNotice(null);
                }}
                className={`flex-1 rounded-md py-1.5 text-xs font-semibold transition-colors ${
                  mode === m
                    ? "bg-brand-emerald text-white"
                    : "text-brand-muted dark:text-brand-darkMuted"
                }`}
              >
                {m === "signin" ? "Sign in" : "Sign up"}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="flex flex-col gap-3">
            {mode === "signup" && (
              <label className="flex flex-col gap-1">
                <span className="text-xs font-medium text-brand-muted dark:text-brand-darkMuted">Your name</span>
                <input
                  type="text"
                  required
                  autoComplete="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="rounded-xl border border-brand-muted/20 bg-transparent px-3 py-2.5 text-sm text-brand-ink outline-none transition focus:border-brand-emerald dark:text-brand-darkInk"
                  placeholder="How should we greet you?"
                />
              </label>
            )}
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-brand-muted dark:text-brand-darkMuted">Email</span>
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="rounded-xl border border-brand-muted/20 bg-transparent px-3 py-2.5 text-sm text-brand-ink outline-none transition focus:border-brand-emerald dark:text-brand-darkInk"
                placeholder="you@example.com"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-brand-muted dark:text-brand-darkMuted">Password</span>
              <input
                type="password"
                required
                minLength={6}
                autoComplete={mode === "signin" ? "current-password" : "new-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="rounded-xl border border-brand-muted/20 bg-transparent px-3 py-2.5 text-sm text-brand-ink outline-none transition focus:border-brand-emerald dark:text-brand-darkInk"
                placeholder="••••••••"
              />
            </label>

            {mode === "signin" && (
              <button
                type="button"
                onClick={forgotPassword}
                className="self-end text-xs text-brand-muted underline dark:text-brand-darkMuted"
              >
                Forgot password?
              </button>
            )}

            {error && (
              <p className="rounded-lg bg-brand-red/10 px-3 py-2 text-xs text-brand-red">{error}</p>
            )}
            {notice && (
              <p className="rounded-lg bg-brand-emerald/10 px-3 py-2 text-xs text-brand-emerald dark:text-brand-emeraldLight">
                {notice}
              </p>
            )}

            <button
              type="submit"
              disabled={busy || !isSupabaseConfigured}
              className="mt-2 rounded-xl bg-brand-emerald py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-brand-emeraldDark disabled:opacity-50"
            >
              {busy ? "…" : mode === "signin" ? "Sign in" : "Create account"}
            </button>
          </form>
        </div>

        <p className="mt-5 text-center text-[11px] text-brand-muted dark:text-brand-darkMuted">
          Your streak and memorization progress are tied to your account, not this
          device — sign in to track them.
        </p>
      </div>
    </div>
  );
}

function GoogleMark() {
  return (
    <svg viewBox="0 0 18 18" className="h-4 w-4 shrink-0" aria-hidden>
      <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.9c1.7-1.57 2.7-3.88 2.7-6.62z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.9-2.26c-.8.54-1.83.86-3.06.86-2.35 0-4.34-1.59-5.05-3.72H.96v2.33A9 9 0 0 0 9 18z" />
      <path fill="#FBBC05" d="M3.95 10.7A5.4 5.4 0 0 1 3.67 9c0-.59.1-1.17.28-1.7V4.97H.96A9 9 0 0 0 0 9c0 1.45.35 2.83.96 4.03l2.99-2.33z" />
      <path fill="#EA4335" d="M9 3.58c1.32 0 2.51.46 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.97l2.99 2.33C4.66 5.17 6.65 3.58 9 3.58z" />
    </svg>
  );
}
