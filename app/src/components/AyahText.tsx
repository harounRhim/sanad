import { useMemo } from "react";
import type { Segment } from "../lib/types";
import { ruleColor } from "../lib/tajweed";

interface Run {
  text: string;
  seg: Segment | null;
}

/**
 * Build character-level runs: assign each char to at most one rule (last write
 * wins on the rare overlap), then group consecutive chars sharing a segment.
 */
function buildRuns(text: string, segments: Segment[]): Run[] {
  const at: (Segment | null)[] = new Array(text.length).fill(null);
  for (const s of segments) {
    const end = Math.min(s.end_idx, text.length);
    for (let i = s.start_idx; i < end; i++) at[i] = s;
  }
  const runs: Run[] = [];
  let cur: Run | null = null;
  for (let i = 0; i < text.length; i++) {
    const seg = at[i];
    if (!cur || cur.seg !== seg) {
      cur = { text: text[i], seg };
      runs.push(cur);
    } else {
      cur.text += text[i];
    }
  }
  return runs;
}

interface Props {
  text: string;
  segments: Segment[];
  tajweed: boolean;
  onSegmentTap?: (seg: Segment) => void;
}

export default function AyahText({ text, segments, tajweed, onSegmentTap }: Props) {
  const runs = useMemo(
    () => (tajweed && segments.length ? buildRuns(text, segments) : [{ text, seg: null }]),
    [text, segments, tajweed]
  );

  return (
    <>
      {runs.map((run, i) =>
        run.seg ? (
          <span
            key={i}
            className="tajweed-seg"
            style={{ color: ruleColor(run.seg.rule) }}
            role="button"
            tabIndex={0}
            title={run.seg.rule}
            onClick={() => onSegmentTap?.(run.seg!)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") onSegmentTap?.(run.seg!);
            }}
          >
            {run.text}
          </span>
        ) : (
          <span key={i}>{run.text}</span>
        )
      )}
    </>
  );
}
