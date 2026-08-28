# Sanad — Product & Design Docs

**Sanad** (سَنَد — *the chain of transmission that certifies a reciter learned
correctly from a verified teacher*) is a Qur'an reading app built on the
Tajweed-Audio-Supabase pipeline in this repo. It renders the Uthmani text with
**color-coded Tajweed rules** and **multi-reciter ayah audio**.

## Documents

| File | What it's for |
|---|---|
| [`PRD.md`](PRD.md) | Product Requirements Document — scope, users, features, data model, success metrics. |
| [`SCREENS.md`](SCREENS.md) | Full screen inventory (the single source of truth both prompts reference). |
| [`STITCH_PROMPT.md`](STITCH_PROMPT.md) | Copy-paste prompt for **Google Stitch** to generate an interactive prototype. |
| [`CLAUDE_DESIGN_IDENTITY_PROMPT.md`](CLAUDE_DESIGN_IDENTITY_PROMPT.md) | Copy-paste prompt for **Claude** to produce the brand identity + design system + all screens. |

## Data layer (already built in this repo)

- **Supabase / PostgreSQL** with `surahs`, `juz`, `pages`, `verses`, `tajweed_segments`, and `ayah_audio` (see `../schema.sql`).
- 6236 ayahs, 18 Tajweed rules, 30 reciters.
- Audio paths stored **relative**; the app prepends a base URL at runtime.

### Two Supabase keys, two roles
| Key | Used by | Notes |
|---|---|---|
| `VITE_SUPABASE_PUBLISHABLE_KEY` (anon/publishable) | the **frontend app** | Safe to ship in the client. Requires **RLS enabled with public read-only policies** on both tables. |
| `service_role` key | the **Python ETL** (`ingest.py`) | Secret — server-side only, never in the client. Goes in the repo `.env` as `SUPABASE_KEY`. |

Project URL: `https://your-project-ref.supabase.co`

> **Before the app can read data:** enable RLS on all six tables (`surahs`,
> `juz`, `pages`, `verses`, `tajweed_segments`, `ayah_audio`) and add a `select`
> policy for the `anon` role (read-only). Otherwise the publishable key returns nothing.
