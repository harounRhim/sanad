import { Link } from "react-router-dom";
import { useBookmarks } from "../hooks/useBookmarks";

export default function Bookmarks() {
  const { bookmarks, remove } = useBookmarks();

  return (
    <div className="p-5">
      <h1 className="mb-4 text-xl font-bold">Bookmarks</h1>

      {bookmarks.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-20 text-center text-brand-muted dark:text-brand-darkMuted">
          <span className="text-5xl">🔖</span>
          <p className="font-medium">No bookmarks yet</p>
          <p className="text-sm">Tap “Save” on any ayah while reading.</p>
          <Link to="/surahs" className="mt-2 rounded-xl bg-brand-emerald px-5 py-2.5 text-sm font-semibold text-white">
            Start reading
          </Link>
        </div>
      ) : (
        <ul className="space-y-2">
          {bookmarks.map((b) => (
            <li
              key={`${b.surah}:${b.ayah}`}
              className="flex items-center gap-3 rounded-xl bg-brand-surface p-3.5 shadow-soft dark:bg-brand-darkSurface"
            >
              <Link to={`/read/${b.surah}?ayah=${b.ayah}`} className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-brand-emerald dark:text-brand-goldLight">
                  {b.surah}:{b.ayah}
                </div>
                <div className="quran truncate text-lg">{b.snippet}</div>
              </Link>
              <button
                onClick={() => remove(b.surah, b.ayah)}
                aria-label="Remove"
                className="text-brand-muted hover:text-red-500"
              >
                🗑
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
