# Argos

> "This is Telemachus, your grandson. He just came back from Sparta."

Argos is a voice companion for people living with dementia. When someone starts talking to them, Argos recognizes the visitor's voice and quietly whispers into one earbud who they are, plus one warm detail to talk about.

In Homer's Odyssey, Odysseus returns home after twenty years in disguise. His wife doesn't recognize him. His son doesn't recognize him. The first to recognize him is his old dog, Argos. This app aims to play that role for people who can no longer recognize the people they love.

Our demo family comes from the Odyssey too: the patient is Laertes, Odysseus's elderly father. His visitors are his son Odysseus, his grandson Telemachus and his daughter-in-law Penelope. In the poem, Laertes only recognizes his son when Odysseus names the fruit trees Laertes gave him as a boy. That shared memory is exactly what Argos's memory cue does.

## Repo structure

Argos has two parts that share one database: a **web app** (online dashboard, invitations and all AI work) and a **patient station** (a program on the MacBook that listens, recognizes voices and plays the reminder into the earbud).

```
argos/
├── docs/          decisions: MVP, flows, memory, tech, structure, edge cases, possible features
├── supabase/      database tables and demo seed data, shared by both parts
├── web/           Next.js web app: dashboard, magic-link form, AI work
│   ├── app/       pages: login, dashboard, invite/[token], api
│   ├── components/
│   └── lib/       supabase, ai, elevenlabs, email
├── station/       Python patient station on the MacBook
│   ├── argos_station/   sync, voiceprints, listener, recognizer, player, tracker, recorder
│   └── scripts/         voice recognition test
└── demo/          fictional demo material only (the Odyssey family)
```

Full layout and rules: [docs/structure.md](docs/structure.md).
