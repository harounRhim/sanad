import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useDrillExamples } from "../hooks/useQueries";
import { useAutoRecorder } from "../hooks/useAutoRecorder";
import { blobToWav16kMono } from "../lib/wav";
import { gradeRecitation, isCorrectionConfigured, type GradeReport } from "../lib/correction";
import { ayahPassed, GRADABLE_RULES } from "../lib/grading";
import { TAJWEED_RULES, RULE_GROUPS, RULE_BY_KEY } from "../lib/tajweed";
import Spinner from "../components/Spinner";
import GradedAyah from "../components/GradedAyah";

type AyahStatus = "pass" | "needs_work";
const ADVANCE_DELAY_MS = 1400;

/** Duolingo-style tajweed drills (Roadmap V2 Phase 3): pick ONE rule, recite
 * a few short curated examples in a row, get instant per-word feedback. Uses
 * the SAME continuous auto-recording flow as Practice.tsx (see
 * useAutoRecorder) — just sourced from useDrillExamples(rule) instead of a
 * muṣḥaf page's verses. */
export default function Drills() {
  const [params, setParams] = useSearchParams();
  const rule = params.get("rule");

  if (!rule) return <RulePicker />;
  return <RuleDrill rule={rule} onBack={() => setParams({})} />;
}

function RulePicker() {
  const [, setParams] = useSearchParams();
  return (
    <div className="p-5 pb-24">
      <h1 className="text-xl font-bold">Tajweed drills</h1>
      <p className="mt-1 text-sm text-brand-muted">
        Pick one rule and drill a few short examples until it clicks.
      </p>
      {RULE_GROUPS.map((group) => (
        <div key={group} className="mt-6">
          <h2 className="text-sm font-semibold text-brand-muted">{group}</h2>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {TAJWEED_RULES.filter((r) => r.group === group).map((r) => {
              const gradable = GRADABLE_RULES.has(r.key);
              return (
                <button
                  key={r.key}
                  disabled={!gradable}
                  onClick={() => setParams({ rule: r.key })}
                  className="rounded-xl border border-brand-muted/15 p-3 text-left disabled:opacity-40"
                  style={{ borderInlineStartColor: r.color, borderInlineStartWidth: 4 }}
                  title={gradable ? undefined : "Grading for this rule isn't built yet."}
                >
                  <div className="text-sm font-medium">{r.en}</div>
                  <div className="quran text-lg" dir="rtl">{r.ar}</div>
                  {!gradable && (
                    <div className="mt-1 text-[10px] text-brand-muted">Coming soon</div>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function RuleDrill({ rule, onBack }: { rule: string; onBack: () => void }) {
  const info = RULE_BY_KEY[rule];
  const { data: examples } = useDrillExamples(rule);

  const [idx, setIdx] = useState(0);
  const [grading, setGrading] = useState(false);
  const [report, setReport] = useState<GradeReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<Record<number, AyahStatus>>({});
  const [done, setDone] = useState(false);
  const advanceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const example = examples?.[idx];

  useEffect(() => () => {
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
  }, []);

  const jumpTo = (i: number) => {
    if (!examples || i < 0 || i >= examples.length) return;
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
    setReport(null);
    setError(null);
    setDone(false);
    setIdx(i);
  };

  const advance = () => {
    if (!examples) return;
    if (idx + 1 < examples.length) {
      jumpTo(idx + 1);
    } else {
      setDone(true);
      autoRec.stop();
    }
  };

  const handleSegment = async (blob: Blob) => {
    if (!example) return;
    setGrading(true);
    setError(null);
    try {
      const wav = await blobToWav16kMono(blob);
      const rep = await gradeRecitation(example.surah, example.ayah, wav);
      setReport(rep);
      const passed = ayahPassed(rep);
      setStatus((s) => ({ ...s, [idx]: passed ? "pass" : "needs_work" }));
      if (passed) advanceTimer.current = setTimeout(advance, ADVANCE_DELAY_MS);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Grading failed.");
    } finally {
      setGrading(false);
    }
  };

  const autoRec = useAutoRecorder(handleSegment);

  if (!isCorrectionConfigured) {
    return (
      <div className="p-6">
        <h1 className="text-xl font-bold">Tajweed drills</h1>
        <div className="mt-4 rounded-xl bg-amber-500/15 p-4 text-sm text-amber-800 dark:text-amber-300">
          The correction service isn’t configured. Start the API
          (<code>server/run.ps1</code>) and set{" "}
          <code>VITE_CORRECTION_API_URL</code> in <code>app/.env.local</code>,
          then restart the dev server.
        </div>
      </div>
    );
  }

  return (
    <div className="p-5 pb-24">
      <button onClick={onBack} className="text-sm text-brand-muted underline">
        ‹ All rules
      </button>
      <h1 className="mt-2 text-xl font-bold" style={{ color: info?.color }}>
        {info?.en ?? rule}
      </h1>
      <p className="quran text-lg text-brand-muted" dir="rtl">{info?.ar}</p>
      <p className="mt-1 text-sm text-brand-muted">{info?.desc}</p>

      {!examples ? (
        <div className="mt-6"><Spinner label="Finding examples…" /></div>
      ) : examples.length === 0 ? (
        <p className="mt-6 text-sm text-brand-muted">
          No example āyahs found for this rule yet.
        </p>
      ) : done ? (
        <div className="mt-8 rounded-xl bg-brand-emerald/15 p-5 text-center">
          <p className="text-lg font-semibold">🎉 Drill complete!</p>
          <p className="mt-1 text-sm text-brand-muted">
            You got all {examples.length} example{examples.length > 1 ? "s" : ""} right.
          </p>
          <button
            onClick={onBack}
            className="mt-4 rounded-full bg-brand-emerald px-6 py-2 text-sm font-semibold text-white"
          >
            Choose another rule
          </button>
        </div>
      ) : (
        <>
          {/* Progress dots — tap to jump to that example */}
          <div className="mt-4 flex flex-wrap gap-1.5">
            {examples.map((_, i) => {
              const st = status[i];
              const bg =
                i === idx ? "#0E5A4A" : st === "pass" ? "#2BB673" : st === "needs_work" ? "#E5392B" : "#D8D3C4";
              return (
                <button
                  key={i}
                  onClick={() => jumpTo(i)}
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: bg }}
                />
              );
            })}
          </div>

          {/* The example ayah, colored by feedback once graded */}
          <div className="mt-4 rounded-2xl border border-brand-muted/15 p-5 text-center" dir="rtl">
            {report && report.content_status !== "content_mismatch" ? (
              <GradedAyah text={example!.text} wordScores={report.word_scores} />
            ) : (
              <p className="quran text-3xl leading-loose">{example!.text}</p>
            )}
            <div className="mt-2 text-xs text-brand-muted" dir="ltr">
              {example!.surah}:{example!.ayah} · example {idx + 1} of {examples.length}
            </div>
          </div>

          {/* Continuous listening controls */}
          <div className="mt-6 flex flex-col items-center gap-3">
            {!autoRec.listening ? (
              <button
                onClick={autoRec.start}
                className="rounded-full bg-brand-emerald px-8 py-4 font-semibold text-white shadow-soft"
              >
                🎙 Start drilling
              </button>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <button
                  onClick={autoRec.stop}
                  className="flex items-center gap-2 rounded-full bg-brand-red px-8 py-4 text-white shadow-soft"
                >
                  <span className="h-3 w-3 animate-pulse rounded-full bg-white" />
                  Stop
                </button>
                <div className="h-1.5 w-40 overflow-hidden rounded-full bg-brand-muted/20">
                  <div
                    className="h-full bg-brand-emerald transition-[width]"
                    style={{ width: `${Math.min(100, autoRec.volume * 400)}%` }}
                  />
                </div>
                <p className="text-xs text-brand-muted">
                  {grading ? "Checking…" : "Listening — recite this āyah."}
                </p>
              </div>
            )}
            {report && !grading && ayahPassed(report) && (
              <p className="text-sm text-brand-emerald">✅ Correct!</p>
            )}
            {report && !grading && !ayahPassed(report) && report.content_status !== "content_mismatch" && (
              <p className="text-sm text-brand-red">🔁 Not quite — try this one again.</p>
            )}
            {autoRec.error && <p className="text-sm text-brand-red">{autoRec.error}</p>}
            {error && <p className="text-sm text-brand-red">{error}</p>}
          </div>

          {report?.content_status === "content_mismatch" && (
            <div className="mt-6 rounded-xl bg-amber-500/15 p-4 text-sm text-amber-800 dark:text-amber-300">
              <p className="font-semibold">This doesn’t sound like this āyah.</p>
              {report.decoded_text && (
                <p className="mt-2 text-xs opacity-80" dir="rtl">We heard: {report.decoded_text}</p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
