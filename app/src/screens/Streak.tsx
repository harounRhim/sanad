import { Link } from "react-router-dom";
import { useStreak } from "../hooks/useStreak";
import Spinner from "../components/Spinner";

const DAY_LABEL = ["S", "M", "T", "W", "T", "F", "S"];

function dayLetter(dateStr: string): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  return DAY_LABEL[new Date(y, m - 1, d).getDay()];
}

/** Interface spec §04.7 — Streak & Jokers. Reached from the Journey Map's
 * status-bar lantern. Pure read-out of useStreak — no grading here, just
 * the week-at-a-glance + joker inventory. */
export default function Streak() {
  const streak = useStreak();

  // Streak state is async (Supabase) — don't flash "0 days lit" at someone
  // holding a real streak.
  if (streak.loading) {
    return <div className="p-6"><Spinner label="Loading your streak…" /></div>;
  }

  return (
    <div className="p-5 pb-24">
      <Link to="/" className="text-sm text-brand-muted dark:text-brand-darkMuted">← Journey</Link>
      <h1 className="mt-2 text-xl font-bold">Your streak</h1>

      <div className="mt-4 rounded-2xl border border-brand-muted/15 bg-brand-surface p-4 shadow-soft dark:bg-brand-darkSurface">
        <div className="flex items-center justify-between">
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold tabular-nums">{streak.current}</span>
            <span className="text-sm text-brand-muted dark:text-brand-darkMuted">days lit 🏮</span>
          </div>
          <div className="flex gap-1.5">
            {Array.from({ length: streak.jokerCap }).map((_, i) => (
              <div
                key={i}
                className={`flex h-8 w-8 items-center justify-center rounded-lg border-[1.5px] ${
                  i < streak.jokers
                    ? "border-brand-gold bg-brand-gold/15"
                    : "border-brand-muted/25"
                }`}
                title={i < streak.jokers ? "Joker available" : "Joker slot empty"}
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke={i < streak.jokers ? "#C9A227" : "#8A97A0"}
                  strokeWidth={1.8}
                  className="h-4 w-4"
                >
                  <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" />
                </svg>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-4 flex justify-between gap-1">
          {streak.week.map((d) => (
            <div key={d.date} className="flex flex-1 flex-col items-center gap-1.5">
              <span className="text-[10px] font-bold text-brand-muted dark:text-brand-darkMuted">
                {dayLetter(d.date)}
              </span>
              <div
                className={`flex h-6 w-6 items-center justify-center rounded-full ${
                  d.state === "done"
                    ? "bg-brand-emerald"
                    : d.state === "joker"
                    ? "bg-brand-gold"
                    : d.state === "today"
                    ? "border-2 border-brand-emerald bg-brand-surface dark:bg-brand-darkSurface"
                    : "bg-brand-muted/20"
                }`}
              >
                {(d.state === "done" || d.state === "joker") && (
                  <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.5} className="h-3 w-3">
                    <path d="M4 12l5 5L20 6" />
                  </svg>
                )}
              </div>
            </div>
          ))}
        </div>

        <p className="mt-4 text-center text-xs text-brand-muted dark:text-brand-darkMuted">
          1 joker refills every 7-day streak · caps at {streak.jokerCap} held
        </p>
      </div>

      <p className="mt-4 text-center text-xs text-brand-muted dark:text-brand-darkMuted">
        Longest streak: {streak.longest} day{streak.longest === 1 ? "" : "s"}
      </p>
    </div>
  );
}
