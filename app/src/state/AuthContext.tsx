import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Session, User } from "@supabase/supabase-js";
import { supabase, isSupabaseConfigured } from "../lib/supabase";

interface AuthCtx {
  user: User | null;
  session: Session | null;
  loading: boolean;
  /** Display name from signup (user_metadata.full_name), or the email's
   * local part as a friendly fallback, or null when signed out. */
  displayName: string | null;
  signIn: (email: string, password: string) => Promise<{ error: string | null }>;
  signUp: (
    email: string,
    password: string,
    name?: string
  ) => Promise<{ error: string | null; needsEmailConfirm: boolean }>;
  signInWithGoogle: () => Promise<{ error: string | null }>;
  resetPassword: (email: string) => Promise<{ error: string | null }>;
  updatePassword: (password: string) => Promise<{ error: string | null }>;
  updateEmail: (email: string) => Promise<{ error: string | null }>;
  updateName: (name: string) => Promise<{ error: string | null }>;
  signOut: () => Promise<void>;
}

function nameFrom(user: User | null): string | null {
  if (!user) return null;
  const meta = (user.user_metadata?.full_name as string | undefined)?.trim();
  if (meta) return meta;
  const local = user.email?.split("@")[0];
  return local || null;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(isSupabaseConfigured);

  useEffect(() => {
    if (!isSupabaseConfigured) return;
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  const value = useMemo<AuthCtx>(
    () => ({
      user: session?.user ?? null,
      session,
      loading,
      displayName: nameFrom(session?.user ?? null),
      signIn: async (email, password) => {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        return { error: error?.message ?? null };
      },
      signUp: async (email, password, name) => {
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: name?.trim() ? { data: { full_name: name.trim() } } : undefined,
        });
        return {
          error: error?.message ?? null,
          needsEmailConfirm: !error && !data.session,
        };
      },
      // Redirects the whole page to Google and back — there's no local
      // result to return on success (the browser navigates away before this
      // promise would resolve). onAuthStateChange picks up the session once
      // Supabase's client parses the tokens out of the redirect-back URL.
      signInWithGoogle: async () => {
        const { error } = await supabase.auth.signInWithOAuth({
          provider: "google",
          options: { redirectTo: window.location.origin },
        });
        return { error: error?.message ?? null };
      },
      // Sends the recovery email; the link signs the user in with a special
      // recovery session and lands them on /reset-password (see that screen),
      // where updatePassword() below finishes the job.
      resetPassword: async (email) => {
        const { error } = await supabase.auth.resetPasswordForEmail(email, {
          redirectTo: `${window.location.origin}/reset-password`,
        });
        return { error: error?.message ?? null };
      },
      updatePassword: async (password) => {
        const { error } = await supabase.auth.updateUser({ password });
        return { error: error?.message ?? null };
      },
      // Supabase sends confirmation links (by default to BOTH the old and
      // the new address) — the change only lands after they're clicked, so
      // callers should phrase success as "check your inbox", not "done".
      updateEmail: async (email) => {
        const { error } = await supabase.auth.updateUser({ email });
        return { error: error?.message ?? null };
      },
      // Name lives in user_metadata — updates instantly (no email confirm),
      // and onAuthStateChange refreshes the session so displayName re-derives.
      updateName: async (name) => {
        const { error } = await supabase.auth.updateUser({ data: { full_name: name.trim() } });
        return { error: error?.message ?? null };
      },
      signOut: async () => {
        await supabase.auth.signOut();
      },
    }),
    [session, loading]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
