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
├── docs/                     decisions: mvp, flows, memory, tech, structure,
│                             edge-cases, possible-features
│
├── supabase/                 shared by both parts
│   ├── migrations/           database tables (the contract between web and station)
│   └── seed.sql              the Odyssey demo family
│
├── web/                      Next.js, online
│   ├── CLAUDE.md             web-only rules for agents
│   ├── app/
│   │   ├── login/            dashboard login
│   │   ├── (dashboard)/      people, a person's memory, conversations
│   │   ├── invite/[token]/   magic-link form for invited people
│   │   ├── plan/             live task plan, read from GitHub issues
│   │   └── api/              e.g. "a conversation was uploaded, process it"
│   ├── components/
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

## Station → web handoff

When a conversation ends, the station uploads the recording to Supabase, then **calls a web API endpoint** to start processing: transcription, memory extraction, new reminder.
