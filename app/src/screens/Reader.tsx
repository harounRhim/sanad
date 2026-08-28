import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useVerses, useSegments, useSurah, useAudio } from "../hooks/useQueries";
import { useSettings } from "../state/SettingsContext";
import { usePlayer } from "../state/PlayerContext";
import { useBookmarks } from "../hooks/useBookmarks";
import AyahText from "../components/AyahText";
import TajweedInfoSheet from "../components/TajweedInfoSheet";
import Spinner from "../components/Spinner";
import { setLastRead } from "../lib/lastRead";
import { toArabicDigits } from "../lib/format";
import { reciterName } from "../lib/reciters";
import type { Segment } from "../lib/types";

const BISMILLAH = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ";

export default function Reader() {
  const { surah } = useParams();
  const surahNum = Number(surah) || 1;
  const [params] = useSearchParams();
  const targetAyah = Number(params.get("ayah")) || null;

  const { fontScale, tajweed, defaultReciter } = useSettings();
  const { current, isPlaying, play } = usePlayer();
  const { has, toggle: toggleBookmark } = useBookmarks();

  const { data: meta } = useSurah(surahNum);
  const { data: verses, isLoading } = useVerses(surahNum);
  const { data: segments } = useSegments(surahNum);
  const { data: audio } = useAudio(surahNum, defaultReciter);

  const [sheet, setSheet] = useState<Segment | null>(null);

  // Group segments by ayah for fast lookup.
  const segByAyah = useMemo(() => {
    const m = new Map<number, Segment[]>();
    for (const s of segments ?? []) {
      const arr = m.get(s.ayah) ?? [];
      arr.push(s);
      m.set(s.ayah, arr);
    }
    return m;
  }, [segments]);

  // Scroll to and remember the target ayah.
  useEffect(() => {
    if (targetAyah) {
      setLastRead(surahNum, targetAyah);
      const el = document.getElementById(`ayah-${targetAyah}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      setLastRead(surahNum, 1);
    }
  }, [surahNum, targetAyah, verses]);

  const playAyah = (ayah: number) => {
    if (!audio?.length) return;
    const idx = audio.findIndex((a) => a.ayah === ayah);
    if (idx >= 0) play(audio, idx);
  };

  return (
    <div className="pb-6">
      {/* Sticky top bar */}
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-brand-muted/15 bg-brand-cream/90 px-4 py-3 backdrop-blur dark:bg-brand-dark/90">
        <Link to="/surahs" className="text-sm text-brand-muted">
          ‹ Surahs
        </Link>
        <span className="font-semibold">{meta?.name_tr ?? `Surah ${surahNum}`}</span>
        <Link to="/reciters" className="text-xs text-brand-emerald dark:text-brand-goldLight">
          {reciterName(defaultReciter)}
        </Link>
      </div>

      {/* Surah header */}
      <div className="px-5 py-6 text-center">
        <div className="quran text-3xl text-brand-emerald dark:text-brand-goldLight">
          {meta?.name_ar}
        </div>
        <div className="mt-1 text-xs uppercase tracking-widest text-brand-muted">
          {meta?.name_en} · {meta?.ayah_count} āyāt
        </div>
        {surahNum !== 1 && surahNum !== 9 && (
          <div className="quran mt-4 text-2xl">{BISMILLAH}</div>
        )}
      </div>

      {isLoading && <Spinner label="Loading verses…" />}

      {/* Verses */}
      <div className="px-5">
        {verses?.map((v) => {
          const playing = current?.surah === surahNum && current?.ayah === v.ayah && isPlaying;
          const bookmarked = has(surahNum, v.ayah);
          return (
            <div
              key={v.ayah}
              id={`ayah-${v.ayah}`}
              className={`border-b border-brand-muted/10 py-5 ${
                playing ? "rounded-xl bg-brand-emerald/5" : ""
              }`}
            >
              <p
                className="quran"
                style={{ fontSize: `${1.9 * fontScale}rem` }}
              >
                <AyahText
                  text={v.text}
                  segments={segByAyah.get(v.ayah) ?? []}
                  tajweed={tajweed}
                  onSegmentTap={setSheet}
                />{" "}
                <span className="mx-1 inline-flex h-7 min-w-7 items-center justify-center rounded-full border border-brand-gold/50 px-1 text-sm text-brand-gold">
                  {toArabicDigits(v.ayah)}
                </span>
              </p>

              <div className="mt-3 flex gap-4 text-brand-muted dark:text-brand-darkMuted">
                <button onClick={() => playAyah(v.ayah)} className="text-sm" aria-label="Play">
                  {playing ? "❚❚ Playing" : "▶ Play"}
                </button>
                <button
                  onClick={() => toggleBookmark(surahNum, v.ayah, v.text.slice(0, 40))}
                  className={`text-sm ${bookmarked ? "text-brand-gold" : ""}`}
                >
                  {bookmarked ? "🔖 Saved" : "🔖 Save"}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Surah navigation */}
      <div className="mt-6 flex justify-between px-5 text-sm">
        {surahNum > 1 ? (
          <Link to={`/read/${surahNum - 1}`} className="text-brand-emerald dark:text-brand-goldLight">
            ‹ Previous
          </Link>
        ) : <span />}
        {surahNum < 114 ? (
          <Link to={`/read/${surahNum + 1}`} className="text-brand-emerald dark:text-brand-goldLight">
            Next ›
          </Link>
        ) : <span />}
      </div>

      <TajweedInfoSheet segment={sheet} onClose={() => setSheet(null)} />
    </div>
  );
}
