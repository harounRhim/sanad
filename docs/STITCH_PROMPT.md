# Google Stitch Prompt — Sanad Prototype

Paste the **master prompt** into Google Stitch (Standard or Experimental mode) to
generate the app, then use the **per-screen prompts** to refine individual screens.
Stitch works best with concrete, screen-by-screen instructions and a clear style
statement. Generate in **Mobile** first; duplicate to **Web** after.

---

## Master prompt (paste first)

> Design a calm, elegant, mobile-first **Qur'an reading app** called **Sanad**.
> The app shows the Arabic Uthmani script with **color-coded Tajweed rules** and
> lets users listen to each verse (ayah) in different reciters.
>
> **Brand & style:** spiritual, serene, premium, modern but timeless. Primary
> color deep emerald green (#0E5A4A), secondary warm gold (#C9A227), backgrounds
> soft cream (#F7F3EA) in light mode and deep charcoal-navy (#10161C) in dark
> mode. Rounded cards, generous whitespace, subtle Islamic geometric ornament as
> accents (never loud). Use a large, beautiful Arabic mushaf-style serif for
> Qur'an text and a clean sans-serif for UI. Right-to-left for Arabic content.
> The mood is reverent and focused, not flashy.
>
> **Tajweed coloring:** individual letters/segments inside the Arabic text are
> tinted by rule — reds/oranges for elongation (madd), greens/teals for nasalization
> and merging (ghunnah/idgham), blues/purple for hiding/conversion (ikhfa/iqlab),
> magenta for qalqalah (echo), and muted grey/gold for silent and connecting letters.
>
> **Build these screens** (mobile): Splash, Onboarding (3 slides), Home,
> Surah Index, Reader (the hero screen, with color-coded ayahs and a bottom
> mini audio player), Tajweed Info bottom sheet, Tajweed Legend, full Audio
> Player, Reciters list, Search, Bookmarks, and Settings. Include a bottom tab
> bar: Home, Read, Reciters, Bookmarks, Settings. Show both light and dark mode.

---

## Per-screen prompts

**Home**
> A serene home screen for Sanad. Top: greeting + search bar. A large
> "Continue reading" card showing Surah name in Arabic + Latin, "Ayah 5 of 286",
> and a thin progress bar. Below: an "Ayah of the day" card with short Arabic
> text colored by Tajweed. Quick-action chips: Surahs, Bookmarks, Tajweed Guide.
> A floating mini audio player at the bottom. Cream background, emerald + gold accents.

**Surah Index**
> A searchable list of all 114 surahs. Each row: an ornamental numbered medallion,
> the surah's Arabic name (right-aligned), its Latin name and English meaning, ayah
> count, and a small "Makki/Madani" tag. Top tabs: "Surah" and "Juz'". Sticky search bar.

**Reader (hero screen)**
> The core reading screen. A surah header with the Arabic name, an ornamental
> Bismillah, and a Makki/Madani tag. Then verses in large Uthmani Arabic, RTL,
> with selected letters tinted in Tajweed colors. Each verse ends with a decorative
> circular ayah-number ornament. Tapping a verse reveals a small action row: Play,
> Bookmark, Info, Share. A sticky top bar with surah name + reciter chip + settings
> icon. A bottom mini-player (reciter name, current ayah, play/pause, next). Show the
> currently-playing verse subtly highlighted. Provide light and dark versions.

**Tajweed Info (bottom sheet)**
> A bottom sheet that appears when a colored letter is tapped. Show the highlighted
> segment large, the whole word it belongs to, the rule name in Arabic and English,
> a colored swatch matching the rule, and a one-line explanation. A link: "See all rules".

**Tajweed Legend**
> A reference screen listing 18 Tajweed rules grouped into sections (Madd, Ghunnah & Idghām,
> Ikhfā & Iqlāb, Qalqalah, Special). Each rule: a color swatch, name in Arabic + English,
> a short definition, and a tiny Arabic example. Clean, scannable, calm.

**Audio Player (full screen)**
> A focused full-screen player. Large now-playing area: Surah:Ayah, reciter name and
> avatar. The current ayah's Arabic text below, auto-scrolling. Transport controls:
> previous, play/pause (large), next. A progress scrubber, a speed control (0.75×–2×),
> repeat mode (ayah/range/surah), and a reciter switch button. Deep emerald background,
> gold highlights.

**Reciters**
> A grid/list of 30 Qur'an reciters. Each card: reciter name, a style tag (Murattal or
> Mujawwad), a small play-sample button, and a check on the selected default. A "Set as
> default" action. Elegant, restrained.

**Search**
> A search screen with a prominent field, recent searches, and results showing matching
> surahs (number + Arabic + Latin name) plus a "Go to 2:255" quick jump. Minimal.

**Bookmarks**
> A list of saved ayahs: each row shows Surah:Ayah, a short Arabic snippet, and swipe-to-delete.
> Include a friendly empty state illustration with "No bookmarks yet".

**Settings**
> A settings screen: Theme (System/Light/Dark segmented control), an Arabic font-size slider
> with live Arabic preview, Default reciter, Reader layout (Mushaf / Verse-by-verse), toggles
> for Autoplay next ayah and Tajweed coloring, and an About section. Clean grouped rows.

**Onboarding**
> Three calm onboarding slides for Sanad: (1) "Read the Qur'an beautifully" with Uthmani
> text, (2) "Learn Tajweed by color" showing color-coded letters with a tiny legend,
> (3) "Listen in 30 voices" showing reciter selection. Page dots, Skip, and a final
> "Get started" button. Soft cream/emerald palette.

---

### Tips for Stitch
- Generate **mobile** screens first; then "Adapt to web" for responsive two-column layouts.
- Keep the style statement identical across prompts so screens stay consistent.
- Use the **annotation/edit** feature to nudge colors, spacing, and the Arabic font.
- Export to **Figma** (or copy the front-end code) to hand off to the Claude design pass.
