import { Link } from "react-router-dom";
import { usePlayer } from "../state/PlayerContext";
import { reciterName } from "../lib/reciters";
import { ref } from "../lib/format";

export default function MiniPlayer() {
  const { current, isPlaying, toggle, next, stop } = usePlayer();
  if (!current) return null;

  return (
    <div className="border-t border-brand-muted/15 bg-brand-emerald text-white">
      <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-2.5">
        <Link to="/player" className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">
            {reciterName(current.reciter)}
          </div>
          <div className="text-xs text-white/70">
            Ayah {ref(current.surah, current.ayah)}
          </div>
        </Link>

        <button
          aria-label={isPlaying ? "Pause" : "Play"}
          onClick={toggle}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-white/15 text-lg"
        >
          {isPlaying ? "❚❚" : "▶"}
        </button>
        <button
          aria-label="Next ayah"
          onClick={next}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-lg"
        >
          ⏭
        </button>
        <button
          aria-label="Stop"
          onClick={stop}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-white/10"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
