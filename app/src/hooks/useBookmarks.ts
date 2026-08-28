import { useCallback, useEffect, useState } from "react";
import type { Bookmark } from "../lib/types";

const KEY = "sanad.bookmarks";

function load(): Bookmark[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Bookmark[]) : [];
  } catch {
    return [];
  }
}

export function useBookmarks() {
  const [bookmarks, setBookmarks] = useState<Bookmark[]>(load);

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(bookmarks));
  }, [bookmarks]);

  const has = useCallback(
    (surah: number, ayah: number) =>
      bookmarks.some((b) => b.surah === surah && b.ayah === ayah),
    [bookmarks]
  );

  const toggle = useCallback((surah: number, ayah: number, snippet: string) => {
    setBookmarks((list) => {
      const exists = list.some((b) => b.surah === surah && b.ayah === ayah);
      if (exists) {
        return list.filter((b) => !(b.surah === surah && b.ayah === ayah));
      }
      return [{ surah, ayah, snippet, createdAt: Date.now() }, ...list];
    });
  }, []);

  const remove = useCallback((surah: number, ayah: number) => {
    setBookmarks((list) =>
      list.filter((b) => !(b.surah === surah && b.ayah === ayah))
    );
  }, []);

  return { bookmarks, has, toggle, remove };
}
