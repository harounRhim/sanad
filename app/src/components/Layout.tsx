import { Suspense } from "react";
import { Outlet } from "react-router-dom";
import BottomNav from "./BottomNav";
import MiniPlayer from "./MiniPlayer";
import Spinner from "./Spinner";
import { isSupabaseConfigured } from "../lib/supabase";
import { useMemorization } from "../hooks/useMemorization";

export default function Layout() {
  const { syncBroken } = useMemorization();

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col">
      {!isSupabaseConfigured && (
        <div className="bg-amber-500/90 px-4 py-2 text-center text-xs font-medium text-white">
          Supabase not configured — copy <code>.env.example</code> to{" "}
          <code>.env.local</code> and set your URL + publishable key.
        </div>
      )}

      {/* Progress tables unreachable (user_memorization select failed) —
          most likely schema.sql's per-user block hasn't been run in the
          Supabase SQL editor yet. Say so loudly: the app otherwise looks
          fully functional while persisting nothing. */}
      {isSupabaseConfigured && syncBroken && (
        <div className="bg-brand-red/90 px-4 py-2 text-center text-xs font-medium text-white">
          Progress sync is unavailable — your recitations aren't being saved.
          Run the <code>user_*</code> tables block of <code>schema.sql</code> in
          the Supabase SQL editor.
        </div>
      )}

      <main className="flex-1 overflow-y-auto">
        {/* Nested Suspense so lazy screens swap WITHIN the shell — without
            it the top-level boundary in App.tsx catches the suspension and
            unmounts the whole layout (nav + mini-player flash away) on every
            first visit to a code-split screen. */}
        <Suspense fallback={<div className="p-6"><Spinner label="Loading…" /></div>}>
          <Outlet />
        </Suspense>
      </main>

      <footer className="sticky bottom-0">
        <MiniPlayer />
        <BottomNav />
      </footer>
    </div>
  );
}
