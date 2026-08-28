import { Link } from "react-router-dom";
import { usePlayer } from "../state/PlayerContext";
import { reciterName } from "../lib/reciters";

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];

export default function AudioPlayer() {
  const { current, isPlaying, toggle, next, prev, rate, setRate } = usePlayer();

  if (!current) {
    return (
      <div className="flex flex-col items-center gap-3 py-24 text-center text-brand-muted">
        <span className="text-5xl">🎙</span>
        <p>Nothing playing.</p>
        <Link to="/surahs" className="rounded-xl bg-brand-emerald px-5 py-2.5 text-sm font-semibold text-white">
          Browse surahs
        </Link>
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-col bg-brand-emerald p-6 text-white">
      <Link to={`/read/${current.surah}?ayah=${current.ayah}`} className="text-sm text-white/70">
        ‹ Back to reader
      </Link>

      <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
        <div className="text-sm text-white/70">{reciterName(current.reciter)}</div>
        <div className="text-4xl font-bold">
          {current.surah}:{current.ayah}
        </div>
      </div>

      <div className="mb-6 flex items-center justify-center gap-2">
        {SPEEDS.map((sp) => (
          <button
            key={sp}
            onClick={() => setRate(sp)}
            className={`rounded-full px-3 py-1 text-xs font-semibold ${
              rate === sp ? "bg-white text-brand-emerald" : "bg-white/15"
            }`}
          >
            {sp}×
          </button>
        ))}
      </div>

      <div className="flex items-center justify-center gap-8 pb-8">
        <button onClick={prev} aria-label="Previous" className="text-3xl">
          ⏮
        </button>
        <button
          onClick={toggle}
          aria-label={isPlaying ? "Pause" : "Play"}
          className="flex h-16 w-16 items-center justify-center rounded-full bg-white text-2xl text-brand-emerald"
        >
          {isPlaying ? "❚❚" : "▶"}
        </button>
        <button onClick={next} aria-label="Next" className="text-3xl">
          ⏭
        </button>
      </div>
    </div>
  );
}
