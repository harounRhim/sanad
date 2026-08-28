# Claude Design Prompt — Tartīl Brand Identity & Screens

Paste the prompt below into Claude (e.g. Claude in a design/artifact context, or
Claude Code) to produce a complete **visual identity + design system + high-fidelity
mockups of every screen**. It includes a proposed Tajweed color palette so the
output stays consistent with the real data (18 rules).

> **Tip:** ask for the design system first (one artifact), confirm the palette and
> typography, then ask for the screens in batches (e.g. Reader + Info + Legend first,
> since they share the color-coded text engine).

---

## The prompt

> You are a senior product designer and brand designer. Design the complete visual
> identity and a high-fidelity, responsive UI for **Sanad**, a Qur'an reading app
> that renders the Uthmani Arabic script with **color-coded Tajweed rules** and
> **multi-reciter ayah audio**. Deliver everything as **self-contained HTML + Tailwind
> CSS mockups** (one artifact per screen, plus one design-system artifact), in both
> **light and dark** themes, **mobile-first** and a **responsive web** layout. Use
> real Arabic Uthmani sample text (e.g. Al-Fātiḥah and Āyat al-Kursī) and apply the
> Tajweed colors to the correct letters to demonstrate the system.
>
> ### 1. Brand identity
> - **Name:** Sanad (سَنَد) — "chain of transmission," the traditional
>   certification that a reciter learned correctly from a verified teacher.
>   Design a wordmark pairing the Arabic and Latin name, plus a simple
>   app-icon concept (an abstract calligraphic/geometric mark — no depiction
>   of people or sacred figures).
> - **Personality:** reverent, serene, premium, timeless yet modern, trustworthy,
>   focused. Avoid anything loud, gamified, or cluttered.
> - **Tone of voice:** warm, respectful, encouraging, concise.
>
> ### 2. Color system
> **Core palette**
> - Primary — Deep Emerald `#0E5A4A` (with tints/shades)
> - Secondary — Warm Gold `#C9A227`
> - Light bg — Cream `#F7F3EA`; surfaces `#FFFFFF`
> - Dark bg — Charcoal-Navy `#10161C`; surfaces `#161D25`
> - Text — Ink `#1B2A2A` (light) / `#E8EDEA` (dark); muted greys for secondary text
> - Success/Info/Warn/Error in muted, calm tones
>
> **Tajweed rule palette (18 rules — group by family, keep within these hues).**
> Provide a final swatch set; refine toward a recognized color-coded mushaf where possible:
>
> | Rule (DB key) | English | Proposed color |
> |---|---|---|
> | `madd_2` | Natural prolongation (2) | `#E8A33D` |
> | `madd_246` | Prolongation (2/4/6) | `#F2C14E` |
> | `madd_6` | Necessary prolongation (6) | `#E5392B` |
> | `madd_munfasil` | Separate prolongation | `#F58B3C` |
> | `madd_muttasil` | Connected prolongation | `#E5662E` |
> | `ghunnah` | Nasalization | `#1E9E8A` |
> | `idghaam_ghunnah` | Merging w/ ghunnah | `#2BB673` |
> | `idghaam_no_ghunnah` | Merging w/o ghunnah | `#7FB069` |
> | `idghaam_shafawi` | Labial merging | `#4C9A7A` |
> | `idghaam_mutajanisayn` | Merging (similar) | `#5FA8A0` |
> | `idghaam_mutaqaribayn` | Merging (close) | `#6FB3AB` |
> | `ikhfa` | Hiding | `#3E78B2` |
> | `ikhfa_shafawi` | Labial hiding | `#5B8FD6` |
> | `iqlab` | Conversion | `#7E57C2` |
> | `qalqalah` | Echoing | `#C2407A` |
> | `hamzat_wasl` | Connecting hamza | `#9AA0A6` |
> | `lam_shamsiyyah` | Assimilated lām | `#B0883B` |
> | `silent` | Silent letter | `#C4C7CC` |
>
> Ensure every Tajweed color meets WCAG AA contrast on both cream and dark
> backgrounds; if a hue fails, define a per-theme variant. **Never rely on color
> alone** — pair it with the tap-to-learn sheet and the legend.
>
> ### 3. Typography
> - **Qur'an text:** a faithful mushaf font — e.g. *KFGQPC Uthman Taha Naskh*,
>   *Amiri Quran*, or *Scheherazade New* — large, high line-height, RTL.
> - **UI (Latin):** a clean humanist sans — e.g. *Inter* or *Plus Jakarta Sans*.
> - **UI (Arabic):** *IBM Plex Sans Arabic* or *Noto Naskh Arabic* for labels.
> - Define a type scale, weights, and the dynamic-type behavior for the reader.
>
> ### 4. Design system (first artifact)
> Components: buttons, chips, cards, list rows, bottom sheet, segmented control,
> sliders, tab bar (mobile) + sidebar (web), mini audio player, full audio player
> controls, ornaments (ayah-number medallion, surah header frame, Bismillah),
> the **color-coded text renderer** spec, icons, spacing/radius/elevation tokens,
> and light/dark theming tokens. Show a one-page style sheet.
>
> ### 5. Screens (deliver all — see the inventory)
> Splash · Onboarding (3 slides) · Home · Surah Index · **Reader (hero)** ·
> Tajweed Info bottom sheet · Tajweed Legend · Audio Player (full screen) ·
> Reciters · Search · Bookmarks · Settings · plus shared empty/error/offline states.
> For each: show mobile and the responsive web adaptation, light + dark, and the key
> interactive states (loading skeletons, playing/highlighted ayah, bookmarked,
> selected reciter, empty results).
>
> ### 6. Constraints
> - Mobile-first; web is responsive (two-column reader, persistent sidebar, mini-player).
> - RTL-correct for all Arabic content; mixed LTR/RTL handled gracefully.
> - Reverent treatment of the sacred text: coloring is an overlay only; never alter glyphs.
> - Accessibility: AA contrast, large tap targets, screen-reader labels, reduced-motion option.
>
> Start by presenting the **design system + brand identity** artifact and the final
> Tajweed swatch set. After I confirm, produce the screens in batches.

---

### Context references (share alongside the prompt if asked)
- Data model & rules: `../schema.sql`, and the 18 rule keys above (exactly match `tajweed_segments.rule`).
- Screen details & states: [`SCREENS.md`](SCREENS.md).
- Product scope: [`PRD.md`](PRD.md).
