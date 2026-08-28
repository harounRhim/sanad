# Sanad — Frontend

Vite + React + TypeScript + Tailwind + Supabase app for the Tajweed-Audio
pipeline in this repo. Renders the Uthmani script with color-coded Tajweed,
multi-reciter ayah audio, AI recitation correction, and account-backed
memorization tracking (streak, SM-2 spaced repetition, active slate).

## Setup

```bash
cd app
npm install
cp .env.example .env.local   # then fill in the values
npm run dev
```

### Environment (`.env.local`)
| Var | What |
|---|---|
| `VITE_SUPABASE_URL` | Your Supabase project URL. |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | The **anon / publishable** key (safe in the browser). **Never** the service_role key. |
| `VITE_AUDIO_BASE_URL` | Cloudflare R2/CDN base URL prepended to `ayah_audio.audio_path`. |
| `VITE_CORRECTION_API_URL` | Tajweed correction API (`server/run.ps1`, port 8000 locally). |
| `VITE_GOOGLE_AUTH_ENABLED` | `true` to show "Continue with Google" — needs the provider configured first (see ROADMAP_V2 follow-up #9). |

> **Accounts are mandatory** — streak and memorization progress live in
> Supabase per-user tables, not the browser. The app reads six public
> reference tables (`surahs`, `juz`, `pages`, `verses`, `tajweed_segments`,
> `ayah_audio` — RLS with public `select`) and three per-user tables
> (`user_memorization`, `user_streak`, `user_active_slate` — RLS scoped to
> `auth.uid()`). Run **all** of `../schema.sql` in the Supabase SQL editor,
> then populate reference data with the Python ETL
> (`python -m tajweed.ingest --all-rules --seed-meta --seed-audio`).
> If the `user_*` tables are missing, the app shows a red "progress sync is
> unavailable" banner and persists nothing.

## Scripts
- `npm run dev` — dev server (http://localhost:5173)
- `npm run build` — production build to `dist/` (route-split; vendor chunks pinned in `vite.config.ts`)
- `npm run preview` — serve the build
- `npm run typecheck` — `tsc --noEmit`

## Structure
```
src/
  lib/        supabase client, types, tajweed rules, reciters, audio URLs,
              correction API client, SM-2 scheduler, pause detector, tiers
  hooks/      React Query data hooks; account-backed useMemorization /
              useStreak / useActiveSlate; recorders (auto + rolling);
              useBookmarks (localStorage — device-local on purpose)
  state/      Settings + audio Player + Auth contexts
  components/ Layout (+sync banner), BottomNav, MiniPlayer, RequireAuth,
              ErrorBoundary, AyahText, GradedAyah/GradedSurah, SessionSummary
  screens/    Journey (home), SurahDetail, Practice, ListenRepeat, Review,
              Drills, DueForRework, Streak, Reader, Search, SurahIndex,
              Reciters, Bookmarks, Settings, TajweedLegend, AudioPlayer,
              Login, ResetPassword
```

## Notes
- All screens except Journey/Login are lazy-loaded (`React.lazy` in `App.tsx`);
  keep new routes lazy unless they're a landing surface.
- The **color-coded renderer** (`components/AyahText.tsx`) overlays rule colors
  on `verse.text[start_idx:end_idx]` — the offsets the ETL guarantees.
- Progress mutators (`recordReview`, `recordActivity`, slate ops) update the
  React Query cache synchronously and upsert to Supabase in the background —
  always read/compound state from the cache, never a render closure.
- `docs/ROADMAP_V2.txt` is the running build log; add an entry per change.
