import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  useSurahs,
  useJuz,
  usePages,
  useVerseSearch,
} from "../hooks/useQueries";
import { isArabic, normalizeArabic } from "../lib/arabic";
import Spinner from "../components/Spinner";

/** Tiny debounce so we don't query Supabase on every keystroke. */
function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

export default function Search() {
  const [raw, setRaw] = useState("");
  const q = useDebounced(raw.trim());

  const { data: surahs } = useSurahs();
  const { data: juz } = useJuz();
  const { data: pages } = usePages();
  const { data: results, isFetching, error } = useVerseSearch(q);

  // --- Direct "jump to" intents parsed from the query ----------------------
  const jumps = useMemo(() => {
    const out: { label: string; sub: string; to: string }[] = [];
    if (!q) return out;

    const verse = q.match(/^(\d{1,3})\s*[:\s]\s*(\d{1,3})$/);
    if (verse) {
      const [s, a] = [Number(verse[1]), Number(verse[2])];
      out.push({ label: `Āyah ${s}:${a}`, sub: "Go to verse", to: `/read/${s}?ayah=${a}` });
    }
    const juzM = q.match(/^juz['ʾ\s]*(\d{1,2})$/i);
    if (juzM && juz) {
      const n = Number(juzM[1]);
      const j = juz.find((x) => x.juz === n);
      if (j)
        out.push({
          label: `Juz' ${n}`,
          sub: `${j.start_surah}:${j.start_ayah}`,
          to: `/read/${j.start_surah}?ayah=${j.start_ayah}`,
        });
    }
    const pageM = q.match(/^(?:page|p)\s*(\d{1,3})$/i);
    if (pageM && pages) {
      const n = Number(pageM[1]);
      const p = pages.find((x) => x.page === n);
      if (p)
        out.push({
          label: `Page ${n}`,
          sub: `${p.start_surah}:${p.start_ayah}`,
          to: `/read/${p.start_surah}?ayah=${p.start_ayah}`,
        });
    }
    return out;
  }, [q, juz, pages]);

  // --- Surah name / number matches (client-side over cached list) ----------
  const surahHits = useMemo(() => {
    if (!q || !surahs) return [];
    const t = q.toLowerCase();
    const tn = normalizeArabic(q);
    return surahs
      .filter(
        (s) =>
          String(s.surah) === q ||
          s.name_tr.toLowerCase().includes(t) ||
          s.name_en.toLowerCase().includes(t) ||
          (isArabic(q) && normalizeArabic(s.name_ar).includes(tn))
      )
      .slice(0, 6);
  }, [q, surahs]);

  const surahName = useMemo(() => {
    const m = new Map<number, string>();
    surahs?.forEach((s) => m.set(s.surah, s.name_tr));
    return m;
  }, [surahs]);

  const showEmpty =
    q.length >= 2 && !isFetching && jumps.length === 0 && surahHits.length === 0 && (results?.length ?? 0) === 0;

  return (
    <div className="p-5">
      <h1 className="mb-4 text-xl font-bold">Search</h1>

      <input
        autoFocus
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        placeholder="Verse text, translation, 2:255, juz 5, page 100…"
        className="mb-5 w-full rounded-xl border border-brand-muted/20 bg-brand-surface px-4 py-3 text-sm outline-none focus:border-brand-emerald dark:bg-brand-darkSurface"
        dir={isArabic(raw) ? "rtl" : "ltr"}
      />

      {q.length > 0 && q.length < 2 && (
        <p className="text-sm text-brand-muted">Type at least 2 characters…</p>
      )}

      {jumps.length > 0 && (
        <Section title="Jump to">
          <div className="space-y-2">
            {jumps.map((j) => (
              <Link
                key={j.to + j.label}
                to={j.to}
                className="flex items-center justify-between rounded-xl bg-brand-emerald/10 p-3.5"
              >
                <span className="font-semibold text-brand-emerald dark:text-brand-goldLight">
                  {j.label}
                </span>
                <span className="text-xs text-brand-muted dark:text-brand-darkMuted">{j.sub}</span>
              </Link>
            ))}
          </div>
        </Section>
      )}

      {surahHits.length > 0 && (
        <Section title="Surahs">
          <ul className="space-y-2">
            {surahHits.map((s) => (
              <li key={s.surah}>
                <Link
                  to={`/read/${s.surah}`}
                  className="flex items-center gap-3 rounded-xl bg-brand-surface p-3 shadow-soft dark:bg-brand-darkSurface"
                >
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-emerald/10 text-xs font-bold text-brand-emerald dark:text-brand-goldLight">
                    {s.surah}
                  </span>
                  <span className="flex-1 font-semibold">{s.name_tr}</span>
                  <span className="quran text-lg text-brand-emerald dark:text-brand-goldLight">
                    {s.name_ar}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {isFetching && <Spinner label="Searching…" />}
      {error && (
        <p className="rounded-xl bg-amber-500/10 p-4 text-sm text-amber-700 dark:text-amber-400">
          Search failed. Ensure the verses table has the search columns (re-run the
          ETL after updating <code>schema.sql</code>) and a public <code>select</code> policy.
        </p>
      )}

      {results && results.length > 0 && (
        <Section title={`Verses (${results.length}${results.length === 50 ? "+" : ""})`}>
          <ul className="space-y-2">
            {results.map((v) => (
              <li key={`${v.surah}:${v.ayah}`}>
                <Link
                  to={`/read/${v.surah}?ayah=${v.ayah}`}
                  className="block rounded-xl bg-brand-surface p-4 shadow-soft dark:bg-brand-darkSurface"
                >
                  <div className="mb-1 text-xs font-semibold text-brand-emerald dark:text-brand-goldLight">
                    {surahName.get(v.surah) ?? `Surah ${v.surah}`} · {v.surah}:{v.ayah}
                  </div>
                  <p className="quran mb-1 text-right text-lg leading-loose" dir="rtl">
                    {v.text}
                  </p>
                  {v.translation && (
                    <p className="text-sm text-brand-muted dark:text-brand-darkMuted">
                      {v.translation}
                    </p>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {showEmpty && (
        <p className="mt-6 text-center text-sm text-brand-muted">
          No matches for “{q}”.
        </p>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-brand-muted">
        {title}
      </h2>
      {children}
    </div>
  );
}
