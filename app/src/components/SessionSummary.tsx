import { Link } from "react-router-dom";

interface Props {
  /** Fraction (0-1) of the sūrah now mastered, for the illumination ring. */
  ratio: number;
  confirmed: number;
  needsWork: number;
  streakDays: number;
  /** Where "Keep going" leads (e.g. back into Listen & Repeat, or the next sūrah). */
  keepGoingTo: string;
  keepGoingLabel?: string;
  backTo: string;
}

/** Interface spec §04.5 — Session Summary. Closes the loop that used to just
 * end with a completion banner: shows what was gained this session in the
 * same "light" language as the Journey Map (an illumination ring, not a
 * score to chase). Reusable so both Listen & Repeat and, later, Practice's
 * own completion state can share it. */
export default function SessionSummary({
  ratio,
  confirmed,
  needsWork,
  streakDays,
  keepGoingTo,
  keepGoingLabel = "Keep going",
  backTo,
}: Props) {
  const pct = Math.round(ratio * 100);
  return (
    <div className="p-6 pb-24 text-center">
      <p className="text-lg font-semibold">Session complete</p>
      <div
        className="mx-auto mt-4 flex h-[130px] w-[130px] items-center justify-center rounded-full"
        style={{ background: `conic-gradient(#C9A227 0 ${pct}%, #DDD5C3 ${pct}% 100%)` }}
      >
        <div className="flex h-[100px] w-[100px] flex-col items-center justify-center rounded-full bg-brand-cream dark:bg-brand-dark">
          <span className="text-2xl font-bold tabular-nums">{pct}%</span>
          <span className="text-[10px] uppercase tracking-wide text-brand-muted dark:text-brand-darkMuted">
            illuminated
          </span>
        </div>
      </div>

      <div className="mx-auto mt-6 max-w-xs divide-y divide-brand-muted/15 text-left text-sm">
        <div className="flex justify-between py-2.5">
          <span className="text-brand-muted dark:text-brand-darkMuted">Āyahs confirmed</span>
          <b className="tabular-nums">{confirmed}</b>
        </div>
        <div className="flex justify-between py-2.5">
          <span className="text-brand-muted dark:text-brand-darkMuted">Needs another pass</span>
          <b className="tabular-nums">{needsWork}</b>
        </div>
        <div className="flex justify-between py-2.5">
          <span className="text-brand-muted dark:text-brand-darkMuted">Streak</span>
          <b className="tabular-nums">{streakDays} day{streakDays === 1 ? "" : "s"} 🏮</b>
        </div>
      </div>

      <Link
        to={keepGoingTo}
        className="mt-6 block rounded-full bg-brand-emerald px-6 py-3.5 text-center font-semibold text-white shadow-soft"
      >
        {keepGoingLabel}
      </Link>
      <Link
        to={backTo}
        className="mt-2 block rounded-full px-6 py-3 text-center text-sm font-semibold text-brand-muted dark:text-brand-darkMuted"
      >
        Back to journey
      </Link>
    </div>
  );
}
