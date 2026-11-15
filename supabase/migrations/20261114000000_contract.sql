-- J0.1 contract: the tables and storage buckets shared by web/ and station/.
-- Shape, paths and who reads or writes what: docs/structure.md.
-- Memory model: docs/memory.md. Flows: docs/flows.md.

-- Helpers ---------------------------------------------------------------

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- Dashboard users ----------------------------------------------------------
-- One row per Supabase Auth user who may use the dashboard (patient and
-- closest person in the MVP). Rows are added by hand; there is no sign-up.

create table public.users (
  id         uuid primary key references auth.users (id) on delete cascade,
  name       text not null,
  created_at timestamptz not null default now()
);

-- True when the signed-in user is a dashboard user. Used by every RLS policy.
create or replace function public.is_dashboard_user()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (select 1 from public.users where id = auth.uid());
$$;

-- People -----------------------------------------------------------------
-- Everyone the patient talks to, plus the patient (is_patient = true).

create table public.people (
  id                uuid primary key default gen_random_uuid(),
  name              text not null,
  relationship      text,                       -- to the patient; null for the patient
  is_patient        boolean not null default false,
  photo_path        text,                       -- path in the "photos" bucket
  voice_sample_path text,                       -- path in the "voice-samples" bucket; a new upload gets a new path
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

create unique index people_one_patient on public.people (is_patient) where is_patient;

create trigger people_set_updated_at
  before update on public.people
  for each row execute function public.set_updated_at();

-- Conversations ----------------------------------------------------------
-- Inserted by the station after the recording is uploaded. The station picks
-- the id so it can use it in the recording path. The web app moves status on.

create table public.conversations (
  id             uuid primary key default gen_random_uuid(),
  started_at     timestamptz not null,
  ended_at       timestamptz not null,
  recording_path text not null,                 -- path in the "recordings" bucket
  status         text not null default 'uploaded'
                 check (status in ('uploaded', 'processing', 'processed', 'failed')),
  error          text,                          -- set when status = 'failed'
  created_at     timestamptz not null default now()
);

-- Which registered visitors were in a conversation (two visitors at once is
-- one conversation with two rows here).
create table public.conversation_people (
  conversation_id uuid not null references public.conversations (id) on delete cascade,
  person_id       uuid not null references public.people (id) on delete cascade,
  primary key (conversation_id, person_id)
);

create index conversation_people_person_id on public.conversation_people (person_id);

-- Memory items -----------------------------------------------------------
-- kind:
--   fact          stable things ("lives in Sparta")
--   shared_memory old moments with the patient ("the fruit trees")
--   recent_event  time-sensitive news; read as a fact once occurred_on is
--                 more than 30 days ago
--   follow_up     from a conversation: plans, promises, topics, what the
--                 patient enjoyed (highest hook priority)
-- source_conversation_id: null = registration or dashboard.
-- told_by_person_id: null = first-hand; set = second-hand (who said it),
--                    lower priority and does not stand out in the dashboard.

create table public.memory_items (
  id                     uuid primary key default gen_random_uuid(),
  person_id              uuid not null references public.people (id) on delete cascade,
  kind                   text not null
                         check (kind in ('fact', 'shared_memory', 'recent_event', 'follow_up')),
  content                text not null,
  occurred_on            date not null default current_date,
  source_conversation_id uuid references public.conversations (id) on delete set null,
  told_by_person_id      uuid references public.people (id) on delete set null,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);

create index memory_items_person_id on public.memory_items (person_id);
create index memory_items_source_conversation_id on public.memory_items (source_conversation_id);

create trigger memory_items_set_updated_at
  before update on public.memory_items
  for each row execute function public.set_updated_at();

-- Invitations ------------------------------------------------------------
-- One-time magic link. Only the SHA-256 hash of the token is stored; the raw
-- token is only in the email. A new invitation is a new row.

create table public.invitations (
  id         uuid primary key default gen_random_uuid(),
  email      text not null,
  token_hash text not null unique,
  invited_by uuid references public.users (id) on delete set null,
  expires_at timestamptz not null default now() + interval '7 days',
  used_at    timestamptz,
  person_id  uuid references public.people (id) on delete set null,  -- set when the form is submitted
  created_at timestamptz not null default now()
);

-- Transcripts ------------------------------------------------------------

create table public.transcripts (
  id              uuid primary key default gen_random_uuid(),
  conversation_id uuid not null unique references public.conversations (id) on delete cascade,
  text            text not null,
  segments        jsonb,                        -- speaker-separated segments from Scribe
  created_at      timestamptz not null default now()
);

-- Reminders --------------------------------------------------------------
-- A new row each time a person's reminder is regenerated; the newest row per
-- person is the current one. The row is inserted only after the audio is
-- uploaded. hook_memory_item_id lets the next one avoid the same hook.

create table public.reminders (
  id                  uuid primary key default gen_random_uuid(),
  person_id           uuid not null references public.people (id) on delete cascade,
  text                text not null,
  hook_memory_item_id uuid references public.memory_items (id) on delete set null,
  audio_path          text not null,            -- path in the "reminder-audio" bucket
  created_at          timestamptz not null default now()
);

create index reminders_person_id_created_at on public.reminders (person_id, created_at desc);

-- Row level security -----------------------------------------------------
-- On for every table. Dashboard users get full access; nobody else does.
-- The web server (magic-link form, processing) and the station use the
-- secret key, which bypasses RLS.

alter table public.users               enable row level security;
alter table public.people              enable row level security;
alter table public.conversations       enable row level security;
alter table public.conversation_people enable row level security;
alter table public.memory_items        enable row level security;
alter table public.invitations         enable row level security;
alter table public.transcripts         enable row level security;
alter table public.reminders           enable row level security;

create policy "dashboard users: full access" on public.users
  for all to authenticated using (public.is_dashboard_user()) with check (public.is_dashboard_user());
create policy "dashboard users: full access" on public.people
  for all to authenticated using (public.is_dashboard_user()) with check (public.is_dashboard_user());
create policy "dashboard users: full access" on public.conversations
  for all to authenticated using (public.is_dashboard_user()) with check (public.is_dashboard_user());
create policy "dashboard users: full access" on public.conversation_people
  for all to authenticated using (public.is_dashboard_user()) with check (public.is_dashboard_user());
create policy "dashboard users: full access" on public.memory_items
  for all to authenticated using (public.is_dashboard_user()) with check (public.is_dashboard_user());
create policy "dashboard users: full access" on public.invitations
  for all to authenticated using (public.is_dashboard_user()) with check (public.is_dashboard_user());
create policy "dashboard users: full access" on public.transcripts
  for all to authenticated using (public.is_dashboard_user()) with check (public.is_dashboard_user());
create policy "dashboard users: full access" on public.reminders
  for all to authenticated using (public.is_dashboard_user()) with check (public.is_dashboard_user());

-- Storage buckets --------------------------------------------------------
-- All private. Path layout: docs/structure.md.

insert into storage.buckets (id, name, public, file_size_limit)
values
  ('photos',         'photos',         false, 10485760),   -- 10 MB
  ('voice-samples',  'voice-samples',  false, 10485760),   -- 10 MB
  ('recordings',     'recordings',     false, 52428800),   -- 50 MB (free-plan limit; upload compressed audio)
  ('reminder-audio', 'reminder-audio', false, 5242880);    -- 5 MB

create policy "dashboard users: full access to argos buckets" on storage.objects
  for all to authenticated
  using (
    bucket_id in ('photos', 'voice-samples', 'recordings', 'reminder-audio')
    and public.is_dashboard_user()
  )
  with check (
    bucket_id in ('photos', 'voice-samples', 'recordings', 'reminder-audio')
    and public.is_dashboard_user()
  );
