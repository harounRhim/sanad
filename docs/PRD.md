# PRD — Sanad (Qur'an Tajweed Reader)

**Status:** Draft v1 · **Date:** 2026-06-29 · **Owner:** Haroun Rhim

---

## 1. Summary

Sanad is a mobile-first (and web) Qur'an reading app that displays the Uthmani
script with **color-coded Tajweed rules** and lets users **listen to any ayah in
any of 30 reciters**. It turns the structured data already produced by this repo's
ETL pipeline (`tajweed_segments`, `ayah_audio` in Supabase) into a calm, beautiful,
learning-oriented reading experience.

## 2. Problem & opportunity

Most Qur'an apps either (a) show plain text with no Tajweed guidance, or (b) show
a static color-coded image that can't be searched, resized, or read aloud word by
word. We already have **per-character Tajweed annotations** and **per-ayah audio
for 30 reciters** in a relational DB — a foundation few apps have. The opportunity
is a reader that is simultaneously *beautiful*, *educational* (teaches Tajweed by
color + legend), and *accessible* (dynamic type, audio, dark mode).

## 3. Goals & non-goals

**Goals (MVP)**
- Read any surah/ayah in Uthmani script with live Tajweed coloring.
- Tap a rule-colored segment to learn which rule applies and why.
- Play ayah audio; switch reciter; continuous play across a surah.
- Browse all 114 surahs; jump to surah:ayah; resume "last read".
- Bookmark ayahs; a clear Tajweed rules legend/guide.
- Light & dark themes; adjustable Arabic font size.

**Non-goals (MVP)**
- Translations & tafsir (planned later; not in MVP data).
- Word-by-word translation/transliteration (data not in current schema).
- Accounts/sync across devices (use local storage first).
- Offline audio download manager (stream first).
- Memorization (hifz) tools, quizzes.

## 4. Target users

| Persona | Need |
|---|---|
| **Learner** improving Tajweed | See *which* rule applies *where*, with explanations and audio to imitate. |
| **Daily reciter** | Fast, calm reading with a favorite reciter and "continue where I left off". |
| **Teacher** | A clean reference to point students to specific rules in specific ayahs. |

## 5. Data model (already implemented — `../schema.sql`)

- **`tajweed_segments`** — `surah, ayah, rule, start_idx, end_idx, segment, word`.
  One row per annotated segment; offsets index into the Uthmani verse text.
- **`ayah_audio`** — `surah, ayah, reciter, audio_path`. One row per (verse, reciter).
- **`surahs`** — `surah, name_ar, name_en, name_tr, ayah_count, revelation_place`.
  One row per surah (114). Source: `Data/audio/data/quran_.json` + standard
  (Tanzil) Makki/Madani classification.
- **`juz`** — `juz, start_surah, start_ayah, end_surah, end_ayah`. One row per
  juz (30); standard boundaries. Powers the Surah Index "Juz'" tab and jump-to-juz.
- **`pages`** — `page, start_surah, start_ayah, end_surah, end_ayah`. One row per
  Madani-mushaf page (604; Tanzil/King Fahd Complex layout). Powers the mushaf
  page-by-page reading mode and "page N of 604" navigation.
- **`verses`** — `surah, ayah, text`. The Uthmani verse text (6236 rows). Source:
  `quran-uthmani.txt` — **this exact text** is what `tajweed_segments.start_idx/
  end_idx` index into, so the client overlays colors on `text[start_idx:end_idx]`.

All four tables are loaded by the ETL (`python -m tajweed.ingest --seed-meta …`).

**Rendering model:** fetch a verse's text + its segments; for each segment apply a
CSS color class keyed by `rule` over the character range `[start_idx, end_idx)`.
Audio: query `ayah_audio` by `(surah, ayah)`; prepend the configured base URL to
`audio_path`.

## 6. Features (MVP scope)

1. **Reader** — surah view, ayah-by-ayah, Tajweed coloring, ayah actions (play, bookmark, info).
2. **Tajweed info** — tap a colored segment → bottom sheet: rule name, color, short explanation, the affected word.
3. **Audio** — per-ayah play, mini-player, continuous surah playback, reciter switching, playback speed.
4. **Reciters** — pick from 30; set a default; (future) favorites.
5. **Navigation** — surah index, go-to (surah:ayah), juz' index (if data added), last-read resume.
6. **Bookmarks** — save/remove ayahs; bookmarks list.
7. **Tajweed legend** — full guide to the 18 rules with colors and explanations.
8. **Search** — by surah name/number; (future) by text.
9. **Settings** — theme, Arabic font size, default reciter, autoplay, script options.

## 7. Non-functional requirements

- **Performance:** verse + segments render < 100 ms after fetch; lazy-load by surah.
- **Accessibility:** dynamic type, sufficient contrast in both themes, screen-reader labels; never rely on color alone (pair color with the legend + tap-to-learn).
- **Correctness/respect:** Uthmani text rendered with a faithful mushaf font; no edits to sacred text; coloring is an overlay only.
- **Offline-tolerant:** cache recently read surahs and the last reciter's audio.
- **Privacy:** no account required for MVP; preferences stored locally.

## 8. Tech stack (proposed)

- **Frontend:** Vite + React + TypeScript (the `VITE_` env vars confirm Vite), Tailwind CSS.
- **Backend:** Supabase (Postgres + REST/Realtime + Storage for audio).
- **Audio hosting:** **Cloudflare R2** (decided — Supabase free tier's 1GB is far short of the ~36GB audio). Client prepends the Cloudflare base URL (`VITE_AUDIO_BASE_URL`) to the relative `audio_path`. R2 object keys must match `audio_path`; set CORS to allow the app origin.
- **State/data:** Supabase JS client (anon/publishable key) + React Query; local storage for prefs/bookmarks.
- **RLS:** enabled with public `select` policies on `surahs`, `juz`, `pages`, `verses`, `tajweed_segments`, and `ayah_audio`.

## 9. Success metrics

- D1/D7 retention; avg. reading session length.
- % sessions that tap a Tajweed segment (learning engagement).
- Audio plays per session; reciter switches.
- Bookmarks created; "continue reading" resumes.

## 10. Screens

See [`SCREENS.md`](SCREENS.md) for the full inventory used by both design prompts.

## 11. Roadmap

- **v1 (MVP):** reader + Tajweed coloring + audio + reciters + bookmarks + legend + settings.
- **v1.1:** translations & tafsir, full-text search, juz'/page navigation.
- **v1.2:** word-by-word (requires extending the ETL), offline audio downloads, accounts + cloud sync.
- **v2:** hifz/memorization mode, recitation recording & self-check.

## 12. Open questions

1. ~~Where is audio hosted?~~ **Decided: Cloudflare R2.** Remaining: the public base URL / custom domain to use.
2. ~~Verse text + surah metadata: Supabase or static?~~ **Decided: Supabase** (`verses` + `surahs` tables, loaded via `--seed-meta`).
3. Default reciter and default theme?
4. Which translation(s) for v1.1, and licensing?
