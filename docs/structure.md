# Repo structure

> Status: **decided** (2026-11-14). Where things live. Tools for each part: [tech.md](tech.md).

```
argos/
├── README.md
├── CLAUDE.md                 entry point for agents: outline + docs table
├── CONTRIBUTING.md
├── .gitignore
├── .env.example              empty template; real keys only in .env
├── .claude/skills/           commit-style
│
├── docs/                     decisions: mvp, flows, memory, tech, design,
│                             structure, edge-cases, possible-features
│
├── supabase/                 shared by both parts
│   ├── config.toml           Supabase CLI settings
│   ├── migrations/           tables, RLS and buckets (the contract between web and station)
│   └── seed.sql              the Odyssey demo family
│
├── web/                      Next.js, online
│   ├── CLAUDE.md             web-only rules for agents
│   ├── app/
│   │   ├── login/            dashboard login
│   │   ├── (dashboard)/      people, a person's memory, invitations, conversations
│   │   ├── invite/[token]/   magic-link form for invited people
│   │   ├── plan/             live task plan, read from GitHub issues
│   │   └── api/              e.g. "a conversation was uploaded, process it"
│   ├── components/
│   │   ├── ui/               shadcn/ui components, themed (design.md)
│   │   └── voice-recorder/   shared voice-sample recorder and checks
│   └── lib/
│       ├── supabase/         database and storage access
│       ├── ai/               reminder sentence + memory extraction
│       │                     (provider in one file: OpenAI now, Google later)
│       ├── elevenlabs/       transcription (Scribe) + reminder voice
│       └── email/            Resend invitations
│
├── station/                  Python, on the MacBook
│   ├── CLAUDE.md             station-only rules for agents
│   ├── argos_station/
│   │   ├── main.py           starts everything
│   │   ├── config.py         folders, .env keys, Supabase client (shared)
│   │   ├── sync.py           pulls people, voice samples, reminder audio
│   │   ├── voiceprints.py    voice sample → voiceprint
│   │   ├── listener.py       mic + speech detection
│   │   ├── recognizer.py     "whose voice is this?"
│   │   ├── player.py         plays the reminder into the AirPod
│   │   ├── tracker.py        conversation start/end, 5 min and 30 min rules
│   │   └── recorder.py       records and uploads the conversation
│   ├── scripts/voice_test.py the first task (see tech.md)
│   └── requirements.txt
│
└── demo/                     fictional demo material only
    └── voice-script.txt      the short text people read for their voice sample
```

## Rules

- **One part per person.** `web/` and `station/` are worked on separately, so changes rarely collide.
- **`supabase/` is the contract.** Both parts read and write the same tables. Talk before changing anything in `supabase/migrations/`, because it affects both parts.
- **Each part has its own `CLAUDE.md`.** An agent working in one part reads that part's rules; the root `CLAUDE.md` stays the entry point.
- **The AI provider lives only in `web/lib/ai/`.** Switching from OpenAI to Google changes that folder only.
- **`demo/` holds fictional material only.** Real voices, photos and conversations go to Supabase storage, never into git.

## The contract

> Decided 2026-11-14 (J0.1). The SQL is in `supabase/migrations/`; this section explains it. Change it only in its own PR, after talking to both tracks.

### Tables

Every table has `id uuid` (primary key) and `created_at`, unless noted.

| Table | Columns | Written by | Read by |
|---|---|---|---|
| `users` | `id` = `auth.users.id`, `name`. One row per dashboard user, added by hand. | by hand | web |
| `people` | `name`, `relationship` (null for the patient), `is_patient` (at most one true), `photo_path`, `voice_sample_path`, `updated_at` | web | web, station |
| `memory_items` | `person_id`, `kind`, `content`, `occurred_on` (date), `source_conversation_id`, `told_by_person_id`, `updated_at` | web | web |
| `invitations` | `email`, `token_hash` (SHA-256 of the link token), `invited_by` → `users`, `expires_at` (default +7 days), `used_at`, `person_id` (set on submit) | web | web |
| `conversations` | `id` (chosen by the station), `started_at`, `ended_at`, `recording_path`, `status` (`uploaded` → `processing` → `processed` / `failed`), `error` | station inserts; web updates `status`, `error` | web |
| `conversation_people` | `conversation_id`, `person_id` (primary key on both). One row per visitor in the conversation. | station | web |
| `transcripts` | `conversation_id` (unique), `text`, `segments` (Scribe speaker segments, jsonb) | web | web |
| `reminders` | `person_id`, `text`, `hook_memory_item_id`, `audio_path` | web | station |

How the rules in [memory.md](memory.md) map onto it:
- **`memory_items.kind`:** `fact`, `shared_memory`, `recent_event`, `follow_up` (from a conversation: plans, promises, topics, what the patient enjoyed). Profile data lives in `people`.
- **Recent events go stale:** a `recent_event` whose `occurred_on` is more than 30 days ago is read as a fact. Computed when read; nothing rewrites rows.
- **Second-hand:** `told_by_person_id` is set to who said it; `created_at` is when. Null means first-hand.
- **Important things from a conversation:** memory items with `source_conversation_id` set. Null means registration or the dashboard.
- **Hook never twice in a row:** compare with the previous reminder's `hook_memory_item_id`.
- **Current reminder:** the newest `reminders` row per person. The web inserts the row only after the audio is uploaded.
- **New voice sample:** each upload gets a new path, so the station recomputes a voiceprint when `voice_sample_path` changes.

**Access (RLS):** on for every table. Signed-in users with a row in `users` get full access (`private.is_dashboard_user()`, kept out of the API); everyone else gets nothing. The web server (magic-link form, processing) and the station use the secret key, which bypasses RLS.

### Storage buckets

All private. The exact path is always stored in the row, so the file format is up to the writer.

| Bucket | Path | Written by | Read by | Size limit |
|---|---|---|---|---|
| `photos` | `{person_id}/{uuid}.{ext}` | web | web | 10 MB |
| `voice-samples` | `{person_id}/{uuid}.{ext}` | web | station | 10 MB |
| `recordings` | `{conversation_id}.{ext}` | station | web | 50 MB |
| `reminder-audio` | `{person_id}/{reminder_id}.mp3` | web | station | 5 MB |

50 MB is the free-plan limit per file, and a 30-minute WAV is larger, so the station uploads recordings compressed (m4a or ogg).

### Station → web handoff: the processing endpoint

When a conversation ends, the station:
1. uploads the recording to `recordings/{conversation_id}.{ext}`,
2. inserts the `conversations` row (`status = 'uploaded'`) and one `conversation_people` row per visitor,
3. calls the endpoint below.

Unknown-voice conversations are not saved, so they never reach this step.

**`POST {ARGOS_WEB_URL}/api/conversations/process`** (`web/app/api/conversations/process/route.ts`)

- **Header:** `Authorization: Bearer <STATION_API_SECRET>`. Both parts have the same value in their env. The web compares it in constant time (`crypto.timingSafeEqual`).
- **Body:** `{ "conversation_id": "<uuid>" }`

| Status | Body | Meaning |
|---|---|---|
| `202` | `{ "conversation_id": "…", "status": "processing" }` | Accepted. The work (transcription, memory extraction, new reminders) runs after the response; `conversations.status` ends as `processed` or `failed`. |
| `200` | `{ "conversation_id": "…", "status": "processing" \| "processed" }` | Already started or done; nothing new happens. Retries are safe. A `failed` conversation can be sent again and gets `202`. |
| `400` | `{ "error": "invalid_request" }` | Missing or malformed `conversation_id`. |
| `401` | `{ "error": "unauthorized" }` | Missing or wrong secret. |
| `404` | `{ "error": "conversation_not_found" }` | No such row. |
| `500` | `{ "error": "internal" }` | Server error. |

The station retries `5xx` and network errors with backoff, and does not retry `4xx`.

### Env keys

One root `.env` (template: [`.env.example`](../.env.example)).
- **Web:** `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `STATION_API_SECRET`, `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `NEXT_PUBLIC_SITE_URL`, `GITHUB_TOKEN`.
- **Station:** `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `ARGOS_WEB_URL`, `STATION_API_SECRET`.
