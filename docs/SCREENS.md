# Screen Inventory — Sanad

The single source of truth for both the Stitch and Claude design prompts. Each
screen lists its purpose, key components, data source, and important states.
Mobile-first; web is a responsive adaptation (two-column reader, persistent sidebar).

---

## 0. Splash
- **Purpose:** brand moment while the app boots / restores last session.
- **Components:** logo/wordmark (Arabic + Latin), subtle calligraphic motif.
- **States:** loading → routes to Home (or Onboarding on first launch).

## 1. Onboarding (first launch only, 3 slides)
- **Purpose:** explain the 3 pillars — read, learn Tajweed by color, listen.
- **Components:** 3 illustrated slides, dots, "Skip", "Get started".
- **Slide 3 CTA:** optional default-reciter + theme pick → Home.

## 2. Home / Today
- **Purpose:** fast entry point.
- **Components:** "Continue reading" card (last surah:ayah + progress), Ayah of the day, quick links (Surahs, Bookmarks, Tajweed guide), search bar, mini-player if audio active.
- **Data:** local last-read; `tajweed_segments`/text for ayah-of-day.
- **States:** first-time (no last-read → show "Start from Al-Fātiḥah").

## 3. Surah Index
- **Purpose:** browse all 114 surahs.
- **Components:** searchable list; each row: number (in ornamental frame), Arabic name, Latin name + meaning, ayah count, Makki/Madani tag. Tabs: *Surah* / *Juz'* (both available — `surahs` and `juz` tables).
- **Data:** `surahs` table (names, counts, makki/madani); `juz` table (30 boundaries) for the Juz' tab.
- **States:** search empty result; scroll-to-letter/number.

## 4. Reader (core screen)
- **Purpose:** read a surah with live Tajweed coloring.
- **Components:**
  - Surah header (name, bismillah, Makki/Madani).
  - Ayah blocks: Uthmani text with **color-coded segments**, ayah-end ornament with number.
  - Per-ayah action row (appears on tap/long-press): **Play**, **Bookmark**, **Info (Tajweed)**, **Share/Copy**.
  - Sticky top bar: surah name, go-to, reciter chip, settings.
  - Bottom **mini-player** when audio plays (reciter, ayah, play/pause, next).
- **Data:** verse text + `tajweed_segments` (overlay by `[start_idx,end_idx)`), `ayah_audio`.
- **States:** loading (skeleton), currently-playing ayah highlighted, bookmarked indicator, two layouts (mushaf page-by-page — backed by the `pages` table, 604 Madani pages — vs "ayah-by-ayah list"), font-size scaling, light/dark.

## 5. Tajweed Info (bottom sheet)
- **Purpose:** explain a tapped colored segment.
- **Components:** the segment shown large, the enclosing **word**, rule name (Arabic + Latin), rule **color swatch**, 1–2 line explanation, "See all rules" → Legend.
- **Data:** the tapped segment's `rule`, `segment`, `word`.

## 6. Tajweed Legend / Guide
- **Purpose:** reference for all **18 rules**.
- **Components:** grouped list (Madd, Ghunnah/Idghām, Ikhfā/Iqlāb, Qalqalah, Special) — each: color swatch, rule name (Arabic + Latin), short definition, a real example ayah. Toggle to apply/preview coloring.
- **Data:** static rule metadata + example refs.

## 7. Audio Player (full screen)
- **Purpose:** focused listening.
- **Components:** large now-playing (surah:ayah, reciter avatar/name), the ayah text, transport (play/pause, prev/next ayah), progress scrubber, speed (0.75–2×), repeat (ayah / range / surah), reciter switch, "follow text" toggle (auto-scroll + highlight).
- **Data:** `ayah_audio` for the surah, base URL + `audio_path`.
- **States:** buffering, playing, paused, error (audio missing → graceful message).

## 8. Reciters
- **Purpose:** choose/preview reciters.
- **Components:** list/grid of 30 reciters (name, style tag e.g. Murattal/Mujawwad, 64kbps note), play sample, "Set as default", current selection check.
- **Data:** reciter list (`reciters.json`), `ayah_audio`.

## 9. Search
- **Purpose:** find a surah / jump to a location.
- **Components:** search field; results: surahs (name/number), "Go to surah:ayah" parser; recent searches. (v1.1: full-text within ayahs.)

## 10. Bookmarks
- **Purpose:** saved ayahs.
- **Components:** list of bookmarked ayahs (surah:ayah, snippet), swipe to remove, tap to open in Reader, empty state.
- **Data:** local storage (MVP).

## 11. Settings
- **Purpose:** preferences.
- **Components:** Theme (System/Light/Dark), Arabic font size slider with live preview, Default reciter, Reader layout (mushaf/list), Autoplay next ayah, Tajweed coloring on/off, Audio base URL/quality (advanced), About, Credits/licenses.

## 12. Error / Empty / Offline states (shared)
- No connection (cached content notice), empty bookmarks, empty search, audio unavailable for an ayah, generic error with retry.

---

### Global components
- **Mini audio player** (persists across screens while playing).
- **Bottom navigation** (mobile): Home · Read · Reciters · Bookmarks · Settings.
- **Sidebar** (web): same destinations + surah quick-jump.
- **Color-coded text renderer** (shared engine used by Reader, Info, Legend, Player).
