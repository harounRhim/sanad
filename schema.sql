-- schema.sql — Schéma Supabase / PostgreSQL pour le pipeline Tajweed.
-- À exécuter UNE fois dans l'éditeur SQL de Supabase avant la première ingestion.
--
--   surahs           : 1 ligne par sourate (noms + nombre d'ayahs + lieu)
--   juz              : 1 ligne par juz (30) avec ses bornes début/fin
--   pages            : 1 ligne par page du mushaf (604) avec ses bornes
--   verses           : 1 ligne par (sourate, ayah) avec le texte uthmani
--   tajweed_segments : 1 ligne par segment annoté (indépendant du récitateur)
--   ayah_audio       : 1 ligne par (verset, récitateur)
--
-- Les contraintes UNIQUE / PRIMARY KEY correspondent aux clés on_conflict
-- utilisées par SupabaseLoader (upserts idempotents) :
--   SURAH_CONFLICT = surah
--   JUZ_CONFLICT   = juz
--   PAGE_CONFLICT  = page
--   VERSE_CONFLICT = surah,ayah
--   SEG_CONFLICT   = surah,ayah,rule,start_idx,end_idx
--   AUDIO_CONFLICT = surah,ayah,reciter

-- ------------------------------------------------------------------- surahs
create table if not exists surahs (
  surah            smallint primary key,
  name_ar          text not null,
  name_en          text not null,
  name_tr          text not null,
  ayah_count       smallint not null,
  revelation_place text not null,          -- 'makki' | 'madani'
  created_at       timestamptz default now()
);

-- ---------------------------------------------------------------------- juz
-- Bornes de chaque juz (para). L'app liste les 30 juz et saute à start_surah:
-- start_ayah ; end_* sert à savoir où il se termine.
create table if not exists juz (
  juz         smallint primary key,
  start_surah smallint not null,
  start_ayah  smallint not null,
  end_surah   smallint not null,
  end_ayah    smallint not null,
  created_at  timestamptz default now()
);

-- --------------------------------------------------------------------- pages
-- Pages du mushaf de Médine (604). L'app affiche « page N / 604 » et permet le
-- saut à start_surah:start_ayah ; mode lecture mushaf page par page.
create table if not exists pages (
  page        smallint primary key,
  start_surah smallint not null,
  start_ayah  smallint not null,
  end_surah   smallint not null,
  end_ayah    smallint not null,
  created_at  timestamptz default now()
);

-- -------------------------------------------------------------------- verses
-- Texte uthmani : c'est CE texte que start_idx/end_idx de tajweed_segments
-- indexent. Le rendu app applique les couleurs sur text[start_idx:end_idx].
--   text_normalized : texte arabe sans diacritiques (recherche tolérante)
--   translation     : traduction anglaise (ayah_en de quran_.json)
--   transliteration : translittération latine (ayah_tr)
create table if not exists verses (
  surah           smallint not null,
  ayah            smallint not null,
  text            text     not null,
  text_normalized text,
  translation     text,
  transliteration text,
  created_at      timestamptz default now(),
  primary key (surah, ayah)
);

-- Si la table existait déjà (schéma antérieur), ajoute les colonnes manquantes.
alter table verses add column if not exists text_normalized text;
alter table verses add column if not exists translation     text;
alter table verses add column if not exists transliteration text;

create index if not exists idx_verses_surah on verses (surah);

-- --------------------------------------------------- recherche plein texte
-- Recherche arabe tolérante (sous-chaîne / fautes de frappe) via trigrammes sur
-- la colonne normalisée ; recherche anglaise via tsvector généré sur la trad.
create extension if not exists pg_trgm;

create index if not exists idx_verses_norm_trgm
  on verses using gin (text_normalized gin_trgm_ops);

alter table verses
  add column if not exists fts tsvector
  generated always as (to_tsvector('english', coalesce(translation, ''))) stored;

create index if not exists idx_verses_fts on verses using gin (fts);

-- Translittération : sous-chaîne tolérante elle aussi.
create index if not exists idx_verses_translit_trgm
  on verses using gin (transliteration gin_trgm_ops);

-- ------------------------------------------------------------------ segments
create table if not exists tajweed_segments (
  id         bigint generated always as identity primary key,
  surah      smallint not null,
  ayah       smallint not null,
  rule       text     not null,
  start_idx  int      not null,
  end_idx    int      not null,
  segment    text     not null,
  word       text     not null,
  created_at timestamptz default now(),
  unique (surah, ayah, rule, start_idx, end_idx)
);

-- Lecture côté app : "tous les segments d'un verset", puis filtrage par règle.
create index if not exists idx_segments_ayah on tajweed_segments (surah, ayah);
create index if not exists idx_segments_rule on tajweed_segments (rule);

-- --------------------------------------------------------------------- audio
create table if not exists ayah_audio (
  surah      smallint not null,
  ayah       smallint not null,
  reciter    text     not null,
  audio_path text     not null,
  verified   boolean  not null default true,  -- false = signalé par audio_verify
  flag_reason text,                            -- ex. "integrity:empty", "review:too_long"
  created_at timestamptz default now(),
  primary key (surah, ayah, reciter)
);

-- Colonnes de correction (ALTER pour les tables déjà créées avant cet ajout).
alter table ayah_audio add column if not exists verified    boolean not null default true;
alter table ayah_audio add column if not exists flag_reason text;

-- Lecture côté app : "tous les récitateurs (vérifiés) d'un verset".
create index if not exists idx_audio_ayah     on ayah_audio (surah, ayah);
create index if not exists idx_audio_verified on ayah_audio (verified);

-- ============================================================================
-- Per-user progress (Sanad — PHASE 6 follow-up #8, accounts made mandatory).
-- Three tables, one per localStorage-backed hook they replace 1:1
-- (useMemorization, useStreak, useActiveSlate) — same field names, just
-- server-side and scoped to auth.uid() via RLS instead of a browser's
-- localStorage. Bookmarks/last-read/settings stay device-local (not asked
-- for, no reason to force a round trip for pure UI preference).
-- ============================================================================

-- ------------------------------------------------------------ user_memorization
-- 1 row per (user, surah, ayah) ever reviewed — mirrors MemorizationEntry.
create table if not exists user_memorization (
  user_id          uuid not null references auth.users(id) on delete cascade,
  surah            smallint not null,
  ayah             smallint not null,
  status           text not null default 'learning',   -- learning|reviewing|mastered
  streak           smallint not null default 0,
  last_reviewed_at timestamptz,
  ease_factor      real not null default 2.5,
  interval_days    real not null default 0,
  repetitions      smallint not null default 0,
  next_review_at   timestamptz,
  primary key (user_id, surah, ayah)
);
alter table user_memorization enable row level security;
-- `drop ... if exists` before each `create policy` so the whole block is
-- safely RE-RUNNABLE (create policy has no "if not exists" form — re-pasting
-- this file would otherwise error on the second run).
drop policy if exists "user_memorization: owner select" on user_memorization;
create policy "user_memorization: owner select" on user_memorization
  for select using (auth.uid() = user_id);
drop policy if exists "user_memorization: owner insert" on user_memorization;
create policy "user_memorization: owner insert" on user_memorization
  for insert with check (auth.uid() = user_id);
drop policy if exists "user_memorization: owner update" on user_memorization;
create policy "user_memorization: owner update" on user_memorization
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ------------------------------------------------------------------ user_streak
-- 1 row per user — mirrors StreakState.
create table if not exists user_streak (
  user_id          uuid primary key references auth.users(id) on delete cascade,
  current          smallint not null default 0,
  longest          smallint not null default 0,
  last_active_date date,
  jokers           smallint not null default 0,
  history          jsonb not null default '{}'::jsonb, -- date -> "done" | "joker"
  updated_at       timestamptz not null default now()
);
alter table user_streak enable row level security;
drop policy if exists "user_streak: owner select" on user_streak;
create policy "user_streak: owner select" on user_streak
  for select using (auth.uid() = user_id);
drop policy if exists "user_streak: owner insert" on user_streak;
create policy "user_streak: owner insert" on user_streak
  for insert with check (auth.uid() = user_id);
drop policy if exists "user_streak: owner update" on user_streak;
create policy "user_streak: owner update" on user_streak
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ------------------------------------------------------------ user_active_slate
-- 1 row per user — mirrors ActiveSlateState. active/cooldowns kept as jsonb
-- arrays (ActiveSlateEntry[] / SlateCooldown[]) rather than normalized rows —
-- always read/written as one whole slate, never queried by sub-field.
create table if not exists user_active_slate (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  active     jsonb not null default '[]'::jsonb,
  cooldowns  jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);
alter table user_active_slate enable row level security;
drop policy if exists "user_active_slate: owner select" on user_active_slate;
create policy "user_active_slate: owner select" on user_active_slate
  for select using (auth.uid() = user_id);
drop policy if exists "user_active_slate: owner insert" on user_active_slate;
create policy "user_active_slate: owner insert" on user_active_slate
  for insert with check (auth.uid() = user_id);
drop policy if exists "user_active_slate: owner update" on user_active_slate;
create policy "user_active_slate: owner update" on user_active_slate
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- --------------------------------------------------------------- client_errors
-- Crash telemetry (lib/errorReporting.ts): ErrorBoundary + window.onerror /
-- unhandledrejection insert here so production errors are visible from the
-- dashboard instead of dying in users' consoles. Insert-only for the user
-- who hit the error (capped client-side at 5/page-load); no select policy —
-- read it from the Supabase dashboard/service role, users never read back.
create table if not exists client_errors (
  id         bigint generated always as identity primary key,
  user_id    uuid references auth.users(id) on delete set null,
  message    text not null,
  stack      text,
  context    text,        -- "render" | "window.error" | "unhandledrejection"
  url        text,        -- pathname only, no query strings (may carry PII)
  user_agent text,
  created_at timestamptz not null default now()
);
alter table client_errors enable row level security;
drop policy if exists "client_errors: owner insert" on client_errors;
create policy "client_errors: owner insert" on client_errors
  for insert with check (auth.uid() = user_id);
