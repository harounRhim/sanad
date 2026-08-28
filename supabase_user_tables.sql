-- ============================================================================
-- Sanad — per-user progress tables. RUN THIS ONCE in the Supabase SQL editor
-- to make the red "Progress sync is unavailable" banner go away.
--
-- HOW:  Supabase dashboard → your project → SQL Editor → New query →
--       paste this whole file → Run.  (Safe to re-run: idempotent.)
--
-- This is the exact same block that lives at the bottom of schema.sql —
-- pulled out on its own so you don't have to find it. Creates the three
-- tables the app writes progress into (memorization, streak, active slate)
-- plus a crash-telemetry table, each locked by RLS so a user only ever
-- sees/writes their OWN rows.
-- ============================================================================

-- ------------------------------------------------------------ user_memorization
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
create table if not exists client_errors (
  id         bigint generated always as identity primary key,
  user_id    uuid references auth.users(id) on delete set null,
  message    text not null,
  stack      text,
  context    text,
  url        text,
  user_agent text,
  created_at timestamptz not null default now()
);
alter table client_errors enable row level security;
drop policy if exists "client_errors: owner insert" on client_errors;
create policy "client_errors: owner insert" on client_errors
  for insert with check (auth.uid() = user_id);

-- After Run succeeds: refresh the app. The red banner disappears and your
-- recitations start saving to your account.
