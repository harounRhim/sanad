import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../state/AuthContext";

/** Landing page for the Supabase password-recovery email link. The link
 * signs the user in with a recovery session before arriving here (the
 * Supabase client parses the tokens out of the URL automatically), so this
 * screen just needs a new-password form on top of `updateUser`. Standalone
 * route OUTSIDE RequireAuth: the recovery session usually satisfies the
 * gate anyway, but if it's expired the user must see an explanation and a
 * way back to /login — not a silent redirect that eats the flow. */
export default function ResetPassword() {
  const auth = useAuth();
  const navigate = useNavigate();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setBusy(true);
    try {
      const { error } = await auth.updatePassword(password);
      if (error) setError(error);
      else navigate("/", { replace: true });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-brand-cream px-5 dark:bg-brand-dark">
      <div className="pointer-events-none absolute -left-24 -top-24 h-72 w-72 rounded-full bg-brand-emerald/15 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-24 -right-16 h-72 w-72 rounded-full bg-brand-gold/20 blur-3xl" />

      <div className="relative w-full max-w-sm">
        <div className="rounded-3xl border border-brand-muted/10 bg-brand-surface/90 p-7 shadow-soft backdrop-blur dark:bg-brand-darkSurface/90">
          <div className="mb-6 text-center">
            <p className="quran text-3xl text-brand-emerald dark:text-brand-emeraldLight">سَنَد</p>
            <h1 className="mt-2 text-lg font-bold text-brand-ink dark:text-brand-darkInk">
              Choose a new password
            </h1>
          </div>

          {!auth.loading && !auth.user && (
            <p className="mb-4 rounded-lg bg-amber-500/10 px-3 py-2 text-center text-xs text-amber-700 dark:text-amber-400">
              This reset link has expired or was already used.{" "}
              <Link to="/login" className="underline">Request a new one from the sign-in page.</Link>
            </p>
          )}

          <form onSubmit={submit} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-brand-muted dark:text-brand-darkMuted">New password</span>
              <input
                type="password"
                required
                minLength={6}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="rounded-xl border border-brand-muted/20 bg-transparent px-3 py-2.5 text-sm text-brand-ink outline-none transition focus:border-brand-emerald dark:text-brand-darkInk"
                placeholder="••••••••"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-brand-muted dark:text-brand-darkMuted">Confirm new password</span>
              <input
                type="password"
                required
                minLength={6}
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="rounded-xl border border-brand-muted/20 bg-transparent px-3 py-2.5 text-sm text-brand-ink outline-none transition focus:border-brand-emerald dark:text-brand-darkInk"
                placeholder="••••••••"
              />
            </label>

            {error && (
              <p className="rounded-lg bg-brand-red/10 px-3 py-2 text-xs text-brand-red">{error}</p>
            )}

            <button
              type="submit"
              disabled={busy || !auth.user}
              className="mt-2 rounded-xl bg-brand-emerald py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-brand-emeraldDark disabled:opacity-50"
            >
              {busy ? "…" : "Set new password"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
