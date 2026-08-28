import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../state/AuthContext";
import Spinner from "./Spinner";

/** Gates every route nested under it on having a signed-in Supabase user —
 * streak and memorization progress live server-side per account now (PHASE 6
 * follow-up #8), so there's no meaningful local-only mode left to fall back
 * to. Redirects to /login, remembering the attempted path so Login can send
 * the user back where they meant to go once signed in. */
export default function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-brand-cream dark:bg-brand-dark">
        <Spinner label="Loading your account…" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}
