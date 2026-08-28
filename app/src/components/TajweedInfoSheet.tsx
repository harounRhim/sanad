import { Link } from "react-router-dom";
import type { Segment } from "../lib/types";
import { RULE_BY_KEY } from "../lib/tajweed";

interface Props {
  segment: Segment | null;
  onClose: () => void;
}

export default function TajweedInfoSheet({ segment, onClose }: Props) {
  if (!segment) return null;
  const rule = RULE_BY_KEY[segment.rule];

  return (
    <div
      className="fixed inset-0 z-40 flex items-end justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-t-3xl bg-brand-surface p-6 shadow-soft dark:bg-brand-darkSurface"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-4 h-1.5 w-12 rounded-full bg-brand-muted/30" />

        <div className="flex items-center justify-between">
          <span
            className="rounded-full px-3 py-1 text-xs font-semibold text-white"
            style={{ backgroundColor: rule?.color ?? "#C9A227" }}
          >
            {rule?.en ?? segment.rule}
          </span>
          <span className="quran text-2xl">{rule?.ar}</span>
        </div>

        <div className="my-5 text-center">
          <div className="quran text-5xl text-brand-emerald dark:text-brand-goldLight">
            {segment.segment}
          </div>
          <div className="quran mt-2 text-2xl text-brand-muted dark:text-brand-darkMuted">
            {segment.word}
          </div>
        </div>

        <p className="text-sm leading-relaxed text-brand-ink/80 dark:text-brand-darkInk/80">
          {rule?.desc}
        </p>

        <div className="mt-6 flex gap-3">
          <Link
            to="/legend"
            className="flex-1 rounded-xl bg-brand-emerald py-3 text-center text-sm font-semibold text-white"
          >
            See all rules
          </Link>
          <button
            onClick={onClose}
            className="flex-1 rounded-xl border border-brand-muted/30 py-3 text-sm font-semibold"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
