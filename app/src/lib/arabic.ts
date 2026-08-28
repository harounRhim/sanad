// Arabic search normalization — MUST mirror src/tajweed/metadata.py:normalize_arabic
// exactly, since queries match against the pre-computed `verses.text_normalized`.
// Ranges below match _ARABIC_MARKS in that file 1:1 (kept as \u escapes on purpose).

const MARKS = new RegExp(
  "[" +
    "ؐ-ؚ" + // quranic / honorific signs
    "ً-ٟ" + // harakat (fathatan, kasra, shadda, sukun…)
    "ٰ" + // dagger alef
    "ۖ-ۜ" + // small high quranic annotations
    "۟-ۨ" +
    "۪-ۭ" +
    "࣓-ࣿ" + // arabic extended annotations
    "ـ" + // tatweel (kashida)
    "]",
  "g"
);

const LETTER_MAP: Record<string, string> = {
  "أ": "ا", // أ -> ا
  "إ": "ا", // إ -> ا
  "آ": "ا", // آ -> ا
  "ٱ": "ا", // ٱ alef wasla -> ا
  "ى": "ي", // ى -> ي
  "ؤ": "و", // ؤ -> و
  "ئ": "ي", // ئ -> ي
  "ة": "ه", // ة -> ه
};

/** Normalize Arabic for tolerant search (strip diacritics, unify letters). */
export function normalizeArabic(input: string): string {
  const stripped = input.replace(MARKS, "");
  let out = "";
  for (const ch of stripped) out += LETTER_MAP[ch] ?? ch;
  return out.replace(/\s+/g, " ").trim();
}

/** True if the string contains any Arabic-script character. */
export function isArabic(s: string): boolean {
  return /[؀-ۿݐ-ݿࢠ-ࣿ]/.test(s);
}

/** Escape PostgREST `ilike` wildcards so user input is treated literally. */
export function escapeLike(s: string): string {
  return s.replace(/[%_\\]/g, (m) => "\\" + m);
}
