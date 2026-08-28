import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useSurahs, useJuz } from "../hooks/useQueries";
import { useMemorization } from "../hooks/useMemorization";
import { useActiveSlate } from "../hooks/useActiveSlate";
import { useStreak } from "../hooks/useStreak";
import { useAuth } from "../state/AuthContext";
import { surahTier, isRetained, type SurahTier } from "../lib/tiers";
import { toArabicDigits } from "../lib/format";
import { hasOnboarded } from "../lib/onboarding";
import type { Surah, Juz } from "../lib/types";
import Spinner from "../components/Spinner";
import OnboardingOverlay from "../components/OnboardingOverlay";

const NODE_MIN = 40;
const NODE_MAX = 68;
const ROW_H = 92;
const AMPLITUDE = 68;
const CENTER_X = 140;
// A node's `y` is NOT its circle's center — `translate(-50%,-50%)` on the
// wrapper centers the WHOLE block (circle + 2-line label below it), which
// has nothing above the circle to balance the label's weight below it. So
// the circle's own visual center sits ABOVE `y` by roughly half the
// label's height+gap (~19px), and a naive "clear the circle's radius from
// y" calculation undershoots by exactly that much — confirmed 2026-07-10 by
// live-measuring getBoundingClientRect() on an actual divider vs its node
// after the first attempt at this STILL overlapped (Juz' 1 over Al-
// Fātiḥa's own circle by ~6px) despite looking correct on paper. Re-derived
// against real measured numbers this time, not just theory:
//   circle's true top  ≈ y − size/2 − 19
//   divider's own height ≈ 21px
// DIVIDER_OFFSET (divider top, measured down from y) must satisfy
// DIVIDER_OFFSET ≥ size/2 + 19 + 21 + margin — worst case (size=NODE_MAX=68
// → radius 34) needs ≥ 34+19+21+6 = 80; DIVIDER_EXTRA_GAP (inserted only at
// an actual Juz' transition, not every node pair — see `nodes` below) must
// then satisfy ROW_H + DIVIDER_EXTRA_GAP − DIVIDER_OFFSET ≥ (previous
// node's own worst-case reach, size/2+19) + margin ≈ 34+19+6 = 59.
const DIVIDER_OFFSET = 85;
const DIVIDER_EXTRA_GAP = 55;

interface MapNode {
  surah: Surah;
  tier: SurahTier;
  active: boolean;
  current: boolean;
  size: number;
  x: number;
  y: number;
  juz: number;
}

/** Which Juz' a sūrah's ĀYAH 1 falls in — the juz' it "begins" in, for
 * grouping/dividers on a per-sūrah map. A sūrah can SPAN several juz' (Al-
 * Baqara covers 1-3), but only one juz' can contain its very first āyah:
 * the last juz' (juz' are in reading order) whose start is at or before
 * this sūrah's āyah 1. Requires `start_ayah <= 1` (i.e. exactly 1) when a
 * juz' starts in this SAME sūrah — otherwise a juz' that starts mid-way
 * through this sūrah (e.g. Juz' 2 at 2:142) would wrongly claim it. */
function juzForSurahStart(surah: number, juzList: Juz[]): number {
  let result = juzList[0]?.juz ?? 1;
  for (const j of juzList) {
    const startsAtOrBefore = j.start_surah < surah || (j.start_surah === surah && j.start_ayah <= 1);
    if (startsAtOrBefore) result = j.juz;
  }
  return result;
}

function hoursUntil(ts: number): number {
  return Math.max(1, Math.round((ts - Date.now()) / 3_600_000));
}

function Header({
  streakCount,
  slotsUsed,
  cap,
  name,
}: {
  streakCount: number | null; // null = still loading — show a dash, not a lying "0"
  slotsUsed: number;
  cap: number;
  name: string | null;
}) {
  return (
    <header className="bg-brand-emerald px-5 pb-6 pt-10 text-white">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-white/70">
            Assalāmu ʿalaykum{name ? `, ${name}` : ""}
          </p>
          <h1 className="mt-1 text-2xl font-bold">
            Sanad <span className="quran text-xl">سَنَد</span>
          </h1>
          <p className="mt-1 text-sm text-white/80">Your journey through the Qur'an.</p>
        </div>
        <Link
          to="/streak"
          className="flex flex-col items-center gap-0.5 rounded-2xl bg-white/10 px-3 py-2"
        >
          <span className="text-lg leading-none">🏮</span>
          <span className="text-sm font-bold tabular-nums">{streakCount ?? "–"}</span>
        </Link>
      </div>
      <div className="mt-4 flex items-center gap-2 text-xs text-white/80">
        <div className="flex gap-1">
          {Array.from({ length: cap }).map((_, i) => (
            <span
              key={i}
              className={`h-1.5 w-1.5 rounded-full ${
                i < slotsUsed ? "bg-brand-goldLight" : "bg-white/25"
              }`}
            />
          ))}
        </div>
        {slotsUsed}/{cap} sūrahs active
      </div>
    </header>
  );
}

/** Tapping a Juz' smooth-scrolls the trail down to that Juz's divider
 * (§04.1's "fast way to jump") — a jump WITHIN the map, not a navigation
 * away from it; the map itself is still where the browsing happens. */
function JuzStrip({ juz }: { juz: { juz: number }[] }) {
  const jumpTo = (juzNum: number) => {
    document.getElementById(`juz-anchor-${juzNum}`)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };
  return (
    <div className="flex gap-2 overflow-x-auto px-5 py-3">
      {juz.map((j) => (
        <button
          key={j.juz}
          onClick={() => jumpTo(j.juz)}
          className="shrink-0 rounded-full border border-brand-muted/25 px-3 py-1.5 text-xs font-medium text-brand-muted dark:border-brand-darkMuted/25 dark:text-brand-darkMuted"
        >
          Juz' {j.juz}
        </button>
      ))}
    </div>
  );
}

/** A quiet horizontal divider marking where a new Juz' begins on the trail
 * — the "little separation with color or a line between the ajzā'" — and
 * the scroll target JuzStrip's buttons jump to. */
function JuzDivider({ juzNum, y }: { juzNum: number; y: number }) {
  return (
    <div
      id={`juz-anchor-${juzNum}`}
      className="absolute left-2 right-2 flex items-center gap-2"
      style={{ top: y }}
    >
      <span className="h-px flex-1 bg-brand-gold/40" />
      <span className="shrink-0 rounded-full border border-brand-gold/40 bg-brand-cream px-2 py-0.5 text-[10px] font-bold text-brand-gold dark:bg-brand-dark dark:text-brand-goldLight">
        Juz' {juzNum}
      </span>
      <span className="h-px flex-1 bg-brand-gold/40" />
    </div>
  );
}

function MapNodeView({
  node,
  slotsOpen,
  nextSlotOpensAt,
}: {
  node: MapNode;
  slotsOpen: number;
  nextSlotOpensAt: number | null;
}) {
  const { surah, tier, active, current, size, x, y } = node;
  // Availability is purely a slate question (does this sūrah occupy one of
  // the six slots right now, and if not, is a slot open to claim/reclaim
  // one) — NOT a question of whether it happens to have zero tracked āyahs
  // yet. A sūrah with real partial progress that's currently outside the
  // slate (e.g. stepped back, see §06) must still read as available-to-
  // resume when slots are open, not as freshly "locked" just because its
  // tier isn't "not_started". Retained is the one tier that always wins.
  const openToStart = tier !== "retained" && !active && slotsOpen > 0;
  const locked = tier !== "retained" && !active && slotsOpen <= 0;

  let circleClasses =
    "flex items-center justify-center rounded-full font-bold shadow-soft transition-transform";
  if (tier === "retained") {
    circleClasses += " bg-brand-gold text-white";
  } else if (current) {
    circleClasses += " bg-brand-emerald text-white ring-4 ring-brand-emerald/30 motion-safe:animate-pulse motion-reduce:animate-none";
  } else if (active) {
    circleClasses += " bg-brand-emerald/80 text-white";
  } else if (openToStart) {
    circleClasses += " border-2 border-brand-emerald text-brand-emerald bg-brand-surface dark:bg-brand-darkSurface";
  } else {
    circleClasses += " border-2 border-brand-muted/30 text-brand-muted/50 bg-black/5 dark:bg-white/5";
  }

  return (
    <div
      id={`map-node-${surah.surah}`}
      className="absolute flex flex-col items-center"
      style={{ left: x, top: y, transform: "translate(-50%, -50%)", width: 96 }}
    >
      <Link
        to={`/surah/${surah.surah}`}
        className="relative flex items-center justify-center"
        style={{ width: size, height: size }}
        aria-label={`${surah.name_tr} — ${tier}`}
      >
        <span className={circleClasses} style={{ width: size, height: size }}>
          <span className="quran text-lg">{toArabicDigits(surah.surah)}</span>
        </span>
        {tier === "retained" && (
          <span className="absolute -right-0.5 -top-0.5 text-xs" aria-hidden>
            ✨
          </span>
        )}
        {current && (
          <span className="absolute -top-5 rounded-full bg-brand-ink px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white dark:bg-brand-darkInk dark:text-brand-dark">
            Here
          </span>
        )}
      </Link>
      <div className="mt-1.5 max-w-[96px] text-center leading-tight">
        <p className="truncate text-[11px] font-semibold text-brand-ink dark:text-brand-darkInk">
          {surah.name_tr}
        </p>
        <p className="quran truncate text-[11px] text-brand-muted dark:text-brand-darkMuted">
          {surah.name_ar}
        </p>
        {locked && <LockedBadge nextSlotOpensAt={nextSlotOpensAt} />}
      </div>
    </div>
  );
}

function LockedBadge({ nextSlotOpensAt }: { nextSlotOpensAt: number | null }) {
  return (
    <p className="mt-0.5 inline-flex items-center gap-1 rounded-full border border-brand-muted/25 bg-brand-surface px-2 py-0.5 text-[9px] font-bold text-brand-muted shadow-soft dark:bg-brand-darkSurface dark:text-brand-darkMuted">
      {nextSlotOpensAt ? `Opens in ~${hoursUntil(nextSlotOpensAt)}h` : "Slots full"}
    </p>
  );
}

/** Interface spec §04.1 — Journey Map, the new Home. A winding trail of every
 * sūrah (programmatic zigzag layout + a straight-segment SVG connector,
 * rather than a hand-authored bezier — same visual idea, robust to render
 * for all 114 nodes). Node state comes straight from existing data
 * (lib/tiers.ts on top of useMemorization) plus the new active-slate/streak
 * hooks (§06) — no new grading logic anywhere on this screen. */
export default function Journey() {
  const { data: surahs } = useSurahs();
  const { data: juz } = useJuz();
  const { entries, loading: memLoading } = useMemorization();
  const slate = useActiveSlate();
  const streak = useStreak();
  const auth = useAuth();
  // First-run guide — shown until the learner picks a sūrah or skips.
  const [showOnboarding, setShowOnboarding] = useState(() => !hasOnboarded());

  const surahAyahCount = useCallback(
    (surah: number) => surahs?.find((s) => s.surah === surah)?.ayah_count ?? 0,
    [surahs]
  );

  // Auto-release any sūrah that has reached Retained since the last check —
  // §06: finishing frees a slot instantly, no cooldown. `slate.pruneRetained`
  // is intentionally in the deps (its identity tracks `slate`'s own state,
  // see useActiveSlate) so this always sweeps against the current slate,
  // not a stale one captured on an earlier render.
  useEffect(() => {
    if (!surahs) return;
    slate.pruneRetained((surah) => isRetained(surah, surahAyahCount(surah), entries));
  }, [surahs, entries, surahAyahCount, slate.pruneRetained]);

  const mostRecentSurah = useMemo(() => {
    if (entries.length === 0) return null;
    return entries.reduce((best, e) => (e.lastReviewedAt > best.t ? { s: e.surah, t: e.lastReviewedAt } : best), {
      s: entries[0].surah,
      t: entries[0].lastReviewedAt,
    }).s;
  }, [entries]);

  const nodes: MapNode[] = useMemo(() => {
    if (!surahs) return [];
    const maxAyahs = Math.max(...surahs.map((s) => s.ayah_count));
    // Running Y accumulator (not a flat `60 + i*ROW_H`) so DIVIDER_EXTRA_GAP
    // only stretches the ~29 gaps that actually carry a Juz' divider,
    // instead of bloating the whole map for the ~85 that don't.
    let y = 100; // clears DIVIDER_OFFSET (85) with a little padding for the very first divider
    let lastJuz: number | null = null;
    return surahs.map((s, i) => {
      const tier = surahTier(s.surah, s.ayah_count, entries);
      const active = slate.isActive(s.surah);
      const size = NODE_MIN + Math.sqrt(s.ayah_count / maxAyahs) * (NODE_MAX - NODE_MIN);
      const side = i % 3 === 1 ? 1 : i % 3 === 2 ? -1 : 0;
      const nodeJuz = juzForSurahStart(s.surah, juz ?? []);
      if (i > 0) y += ROW_H + (nodeJuz !== lastJuz ? DIVIDER_EXTRA_GAP : 0);
      lastJuz = nodeJuz;
      return {
        surah: s,
        tier,
        active,
        current: active && s.surah === mostRecentSurah,
        size,
        x: CENTER_X + side * AMPLITUDE,
        y,
        juz: nodeJuz,
      };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [surahs, entries, slate.active, mostRecentSurah, juz]);

  // One divider per Juz' transition — where a node's juz' differs from the
  // node right before it. Fixed DIVIDER_OFFSET above the node it introduces
  // (not the gap's midpoint) — that node's own circle is the only thing
  // directly below the divider, so a fixed clearance from ITS center is
  // exact regardless of size, unlike a midpoint that has to guess how far
  // the PREVIOUS node's (variable-height) label might reach upward. Also
  // doubles as JuzStrip's scroll target.
  const juzBoundaries = useMemo(() => {
    const out: { juz: number; y: number }[] = [];
    let lastJuz: number | null = null;
    nodes.forEach((n) => {
      if (n.juz !== lastJuz) {
        out.push({ juz: n.juz, y: n.y - DIVIDER_OFFSET });
        lastJuz = n.juz;
      }
    });
    return out;
  }, [nodes]);

  const mapHeight = nodes.length > 0 ? nodes[nodes.length - 1].y + 80 : 0;

  return (
    <div className="pb-24">
      {showOnboarding && (
        <OnboardingOverlay name={auth.displayName} onDone={() => setShowOnboarding(false)} />
      )}

      <Header
        streakCount={streak.loading ? null : streak.current}
        slotsUsed={slate.slotsUsed}
        cap={slate.cap}
        name={auth.displayName}
      />

      {juz && surahs && <JuzStrip juz={juz} />}

      {slate.nextSlotOpensAt && (
        <p className="mx-5 mt-1 text-center text-xs text-brand-muted dark:text-brand-darkMuted">
          A stepped-back slot opens in ~{hoursUntil(slate.nextSlotOpensAt)}h.
        </p>
      )}

      {/* Wait for BOTH the sūrah list and the memorization data — rendering
          the map before progress arrives flashes every node as not_started
          for a beat, then pops them to their real tiers, which reads as the
          user's progress "loading in wrong" on every single app open. */}
      {!surahs || memLoading || slate.loading || streak.loading ? (
        <div className="p-6"><Spinner label="Loading your journey…" /></div>
      ) : (
        <div className="relative mx-auto mt-2" style={{ width: 280, height: mapHeight }}>
          {/* Alternating tint per Juz' section — the "color" half of the
              separation; the line+label divider below is the other half. */}
          {juzBoundaries.map((b, i) =>
            b.juz % 2 === 0 ? (
              <div
                key={`band-${b.juz}`}
                className="absolute left-0 right-0 bg-brand-gold/5"
                style={{ top: b.y, height: (juzBoundaries[i + 1]?.y ?? mapHeight) - b.y }}
              />
            ) : null
          )}
          <svg className="absolute inset-0 overflow-visible" width={280} height={mapHeight}>
            <polyline
              points={nodes.map((n) => `${n.x},${n.y}`).join(" ")}
              fill="none"
              stroke="#C9A227"
              strokeWidth={2}
              strokeDasharray="1 10"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={0.55}
            />
          </svg>
          {nodes.map((n) => (
            <MapNodeView
              key={n.surah.surah}
              node={n}
              slotsOpen={slate.slotsOpen}
              nextSlotOpensAt={slate.nextSlotOpensAt}
            />
          ))}
          {/* Rendered AFTER the nodes so a divider always paints on top of
              (never gets masked by) the node it introduces, even in the
              unlikely event the geometry above is still tight for some
              future node-size tuning. */}
          {juzBoundaries.map((b) => (
            <JuzDivider key={b.juz} juzNum={b.juz} y={b.y} />
          ))}
        </div>
      )}
    </div>
  );
}
