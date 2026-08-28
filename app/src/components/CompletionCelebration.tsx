import { useEffect, useState } from "react";

export type CompletionTier = "first" | "memorizing" | "mastered";

interface Props {
  tier: CompletionTier;
  /** Memorized % before this session and after — the ring animates between. */
  fromPct: number;
  toPct: number;
  surahName: string;
  hasNext: boolean;
  onNext: () => void;
  onClose: () => void;
}

const TIER_COPY: Record<CompletionTier, { icon: string; title: string; sub: (n: string) => string }> = {
  first: {
    icon: "🌱",
    title: "First time through!",
    sub: (n) => `You recited all of ${n} correctly. Come back to review it over the next days and it will take root.`,
  },
  memorizing: {
    icon: "📖",
    title: "Coming along",
    sub: (n) => `Another clean recitation of ${n}. Keep reviewing to move it toward mastery.`,
  },
  mastered: {
    icon: "⭐",
    title: "Mastered — mā shāʾ Allāh!",
    sub: (n) => `${n} is fully memorized. Beautifully done.`,
  },
};

const WALK_MS = 2200;
const COUNT_MS = 1100;

const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Full-screen "you finished the sūrah" celebration for the Recite-now flow:
 * (1) a little figure walks to the mosque, then (2) a tiered result popup with
 * the memorization ring animating up from the session's starting %. */
export default function CompletionCelebration({
  tier,
  fromPct,
  toPct,
  surahName,
  hasNext,
  onNext,
  onClose,
}: Props) {
  const reduce = prefersReducedMotion();
  const [phase, setPhase] = useState<"walking" | "result">("walking");
  const [pct, setPct] = useState(fromPct);

  // Walk → result.
  useEffect(() => {
    const t = setTimeout(() => setPhase("result"), reduce ? 250 : WALK_MS);
    return () => clearTimeout(t);
  }, [reduce]);

  // Count the ring up once the result shows.
  useEffect(() => {
    if (phase !== "result") return;
    if (reduce || toPct === fromPct) {
      setPct(toPct);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / COUNT_MS);
      const eased = 1 - Math.pow(1 - t, 3);
      setPct(Math.round(fromPct + (toPct - fromPct) * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [phase, fromPct, toPct, reduce]);

  const copy = TIER_COPY[tier];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-5 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-3xl bg-brand-cream p-6 text-center shadow-soft dark:bg-brand-darkSurface">
        {phase === "walking" ? (
          <div className="py-4">
            <WalkScene />
            <p className="mt-2 text-sm font-semibold text-brand-emerald dark:text-brand-goldLight">
              On your way…
            </p>
          </div>
        ) : (
          <>
            <div className="text-4xl">{copy.icon}</div>
            <h2 className="mt-2 text-lg font-bold text-brand-ink dark:text-brand-darkInk">{copy.title}</h2>
            <p className="mx-auto mt-1 max-w-xs text-sm text-brand-muted dark:text-brand-darkMuted">
              {copy.sub(surahName)}
            </p>

            <div
              className="mx-auto mt-5 flex h-[128px] w-[128px] items-center justify-center rounded-full"
              style={{ background: `conic-gradient(#0E5A4A 0 ${pct}%, #DDD5C3 ${pct}% 100%)` }}
            >
              <div className="flex h-[98px] w-[98px] flex-col items-center justify-center rounded-full bg-brand-cream dark:bg-brand-dark">
                <span className="text-3xl font-bold tabular-nums text-brand-emerald dark:text-brand-goldLight">
                  {pct}%
                </span>
                <span className="text-[10px] uppercase tracking-wide text-brand-muted dark:text-brand-darkMuted">
                  memorized
                </span>
              </div>
            </div>

            {toPct > fromPct ? (
              <p className="mt-3 text-sm font-semibold text-brand-emerald dark:text-brand-goldLight">
                ↑ {fromPct}% → {toPct}%
              </p>
            ) : (
              <p className="mt-3 text-xs text-brand-muted dark:text-brand-darkMuted">
                Keep reviewing to raise it further.
              </p>
            )}

            <div className="mt-6 flex flex-col gap-2">
              {hasNext && (
                <button
                  onClick={onNext}
                  className="rounded-full bg-brand-emerald px-6 py-3 font-semibold text-white shadow-soft transition hover:bg-brand-emeraldDark"
                >
                  Next sūrah →
                </button>
              )}
              <button
                onClick={onClose}
                className="rounded-full px-6 py-2.5 text-sm font-semibold text-brand-muted dark:text-brand-darkMuted"
              >
                Stay here
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/** A small figure that walks rightward to a mosque (CSS keyframes in
 * index.css). Reduced-motion users get the static end pose — the global
 * `* { animation: none }` rule pins every limb at its 0% frame. */
function WalkScene() {
  return (
    <svg viewBox="0 0 320 180" className="mx-auto w-full max-w-[280px]" role="img" aria-label="Walking to the mosque">
      {/* path */}
      <line x1="0" y1="152" x2="320" y2="152" stroke="#C9A227" strokeOpacity="0.4" strokeWidth="2" strokeDasharray="2 9" />

      {/* mosque */}
      <g>
        <rect x="238" y="98" width="62" height="54" rx="3" fill="#0E5A4A" />
        <path d="M238 98 Q269 62 300 98 Z" fill="#0E5A4A" />
        <rect x="256" y="122" width="26" height="30" rx="13" fill="#0A4034" />
        <rect x="305" y="72" width="10" height="80" rx="2" fill="#137A64" />
        <path d="M305 72 Q310 62 315 72 Z" fill="#0E5A4A" />
        {/* crescent */}
        <path d="M269 54 a7 7 0 1 1 -3.2 -12.8 a5.4 5.4 0 1 0 3.2 12.8 Z" fill="#C9A227" />
      </g>

      {/* walker */}
      <g className="sanad-walker">
        <g className="sanad-bob">
          {/* back leg */}
          <g className="sanad-leg-back">
            <line x1="34" y1="122" x2="34" y2="150" stroke="#0A4034" strokeWidth="4" strokeLinecap="round" />
          </g>
          {/* front leg */}
          <g className="sanad-leg-front">
            <line x1="34" y1="122" x2="34" y2="150" stroke="#0E5A4A" strokeWidth="4" strokeLinecap="round" />
          </g>
          {/* torso (a simple thobe) */}
          <line x1="34" y1="96" x2="34" y2="124" stroke="#137A64" strokeWidth="8" strokeLinecap="round" />
          {/* arm */}
          <g className="sanad-arm-front">
            <line x1="34" y1="102" x2="34" y2="120" stroke="#0E5A4A" strokeWidth="3.5" strokeLinecap="round" />
          </g>
          {/* head */}
          <circle cx="34" cy="88" r="8" fill="#1B2A2A" />
        </g>
      </g>
    </svg>
  );
}
