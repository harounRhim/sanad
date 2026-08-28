import { useMemo } from "react";
import type { WordScore } from "../lib/correction";
import { VERDICT_COLOR } from "../lib/grading";

/** Color each word by its combined content+tajweed verdict (word_scores).
 * A word not covered by any score (e.g. the basmala prefix stripped from
 * ayah 1 — see word_score.py) renders uncolored. Shared by Practice.tsx and
 * Drills.tsx (both grade via the same /grade word_scores shape). */
export default function GradedAyah({ text, wordScores }: { text: string; wordScores: WordScore[] }) {
  const runs = useMemo(() => {
    const at: (WordScore | null)[] = new Array(text.length).fill(null);
    for (const w of wordScores) {
      const end = Math.min(w.end_idx, text.length);
      for (let i = w.start_idx; i < end; i++) at[i] = w;
    }
    const out: { text: string; w: WordScore | null }[] = [];
    let cur: { text: string; w: WordScore | null } | null = null;
    for (let i = 0; i < text.length; i++) {
      const w = at[i];
      if (!cur || cur.w !== w) {
        cur = { text: text[i], w };
        out.push(cur);
      } else cur.text += text[i];
    }
    return out;
  }, [text, wordScores]);

  const titleFor = (w: WordScore) => {
    if (!w.content_ok) return "Not recognized — check the word and pronunciation.";
    if (w.rules.length === 0) return "Correct.";
    return w.rules.map((r) => `${r.rule}: ${r.message}`).join("\n");
  };

  return (
    <p className="quran text-3xl leading-loose">
      {runs.map((run, i) =>
        run.w ? (
          <span
            key={i}
            style={{
              color: VERDICT_COLOR[run.w.verdict],
              borderBottom: `2px solid ${VERDICT_COLOR[run.w.verdict]}`,
            }}
            title={titleFor(run.w)}
          >
            {run.text}
          </span>
        ) : (
          <span key={i}>{run.text}</span>
        )
      )}
    </p>
  );
}
