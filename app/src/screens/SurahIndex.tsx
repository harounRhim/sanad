import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useSurahs, useJuz } from "../hooks/useQueries";
import Spinner from "../components/Spinner";

type Tab = "surah" | "juz";

export default function SurahIndex() {
  const [tab, setTab] = useState<Tab>("surah");
  const [q, setQ] = useState("");
  const { data: surahs, isLoading, error } = useSurahs();
  const { data: juz } = useJuz();

  const filtered = useMemo(() => {
    if (!surahs) return [];
    const t = q.trim().toLowerCase();
    if (!t) return surahs;
    return surahs.filter(
      (s) =>
        s.name_tr.toLowerCase().includes(t) ||
        s.name_en.toLowerCase().includes(t) ||
        s.name_ar.includes(t) ||
        String(s.surah) === t
    );
  }, [surahs, q]);

  return (
    <div className="p-5">
      <h1 className="mb-4 text-xl font-bold">Read</h1>

      <div className="mb-4 inline-flex rounded-xl bg-brand-muted/10 p-1">
        {(["surah", "juz"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-lg px-5 py-1.5 text-sm font-semibold capitalize ${
              tab === t
                ? "bg-brand-surface text-brand-emerald shadow-soft dark:bg-brand-darkSurface dark:text-brand-goldLight"
                : "text-brand-muted"
            }`}
          >
            {t === "juz" ? "Juz'" : "Surah"}
          </button>
        ))}
      </div>

      {tab === "surah" && (
        <>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search surah…"
            className="mb-4 w-full rounded-xl border border-brand-muted/20 bg-brand-surface px-4 py-2.5 text-sm outline-none focus:border-brand-emerald dark:bg-brand-darkSurface"
          />

          {isLoading && <Spinner label="Loading surahs…" />}
          {error && <ErrorHint />}

          <ul className="space-y-2">
            {filtered.map((s) => (
              <li key={s.surah}>
                <Link
                  to={`/read/${s.surah}`}
                  className="flex items-center gap-4 rounded-xl bg-brand-surface p-3 shadow-soft dark:bg-brand-darkSurface"
                >
                  <span className="flex h-9 w-9 shrink-0 rotate-45 items-center justify-center rounded-lg bg-brand-emerald/10 text-sm font-bold text-brand-emerald dark:text-brand-goldLight">
                    <span className="-rotate-45">{s.surah}</span>
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold">{s.name_tr}</div>
                    <div className="text-xs text-brand-muted dark:text-brand-darkMuted">
                      {s.name_en} · {s.ayah_count} āyāt ·{" "}
                      {s.revelation_place === "madani" ? "Madani" : "Makki"}
                    </div>
                  </div>
                  <span className="quran text-xl text-brand-emerald dark:text-brand-goldLight">
                    {s.name_ar}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}

      {tab === "juz" && (
        <ul className="space-y-2">
          {juz?.map((j) => (
            <li key={j.juz}>
              <Link
                to={`/read/${j.start_surah}?ayah=${j.start_ayah}`}
                className="flex items-center justify-between rounded-xl bg-brand-surface p-3.5 shadow-soft dark:bg-brand-darkSurface"
              >
                <span className="font-semibold">Juz' {j.juz}</span>
                <span className="text-xs text-brand-muted dark:text-brand-darkMuted">
                  {j.start_surah}:{j.start_ayah} – {j.end_surah}:{j.end_ayah}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ErrorHint() {
  return (
    <p className="rounded-xl bg-amber-500/10 p-4 text-sm text-amber-700 dark:text-amber-400">
      Couldn't load data. Check Supabase env vars and that RLS has a public{" "}
      <code>select</code> policy on the tables.
    </p>
  );
}
