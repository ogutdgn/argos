# Tech

> Status: **decided** (2026-11-14). Which tools build the MVP in [mvp.md](mvp.md).
> Flows they implement: [flows.md](flows.md). Memory model: [memory.md](memory.md).

## The split

The system has two parts that share one database.

**1. Web app (online, TypeScript)**
- Dashboard and the magic-link form.
- Invitations.
- All AI work: transcription, memory extraction, writing the reminder sentence, making the reminder audio.

**2. Patient station (on the MacBook, Python)**
- Listens to the room through the MacBook mic.
- Recognizes voices.
- Plays the ready-made reminder into the AirPod.
- Records the conversation, decides when it ended (rules in [flows.md](flows.md) and [edge-cases.md](edge-cases.md)), and uploads the recording.

**Reminders are made ahead of time.** Each person's reminder sentence and audio are regenerated whenever their memory changes, so the station never waits for the AI during a conversation.

**Why Python for the station:** voice recognition tools are much stronger in Python than in TypeScript.

## Tools

| Part | Tool |
|---|---|
| Database, file storage (photos, voice samples), dashboard login | **Supabase** |
| Dashboard and magic-link form | **Next.js** on Vercel |
| Styling | **Tailwind CSS v4** + **shadcn/ui**; fonts **Source Serif 4** (headings) and **Source Sans 3** (body). Look and tokens: [design.md](design.md). |
| Dashboard users | Supabase login; users table built for more than 2 users |
| Magic links for invited people | Our own one-time link, stored in the database, expires after 1 week |
| Invitation email | **Resend** (email only) |
| Detecting speech | MacBook mic + **Silero VAD** (station) |
| Voice recognition | **SpeechBrain** voiceprints, on the Mac (station). Fallback: **Picovoice Eagle**. |
| Transcription | **ElevenLabs Scribe** (separates speakers) |
| Reminder sentence and memory extraction | **OpenAI** API (**gpt-5-mini**: cheap, enough for one short sentence and structured extraction) until the demo; **Google** API after. Keep the AI calls in one small module so the provider can be swapped. |
| Reminder voice | **ElevenLabs** text-to-speech, calm and warm voice. Fallback: macOS built-in voice. |

## First task: test voice recognition

Voice recognition is the biggest risk. Test it before building anything around it:
1. Register 3 voices (20–30 seconds each, reading the same short text).
2. Check that a 3–5 second greeting is matched to the right person, and that an unknown voice is not matched.
3. If SpeechBrain is not good enough, switch to Picovoice Eagle early.

## Voice recognition threshold

> Status: **decided** (2026-11-15, S0.2). Used by the station's recognizer (S1.4); voiceprints are made by `station/argos_station/voiceprints.py` with the same method.

- **Threshold: 0.455** cosine similarity, with SpeechBrain ECAPA (`speechbrain/spkrec-ecapa-voxceleb`), 16 kHz mono audio and L2-normalized embeddings. At or above → that person; below → "unknown", say nothing.
- **How it was measured** (2026-11-15, `station/scripts/voice_test.py`):
  - 2 voices enrolled, each 25 s reading `demo/voice-script.txt` on the MacBook Pro Microphone.
  - 3 greetings of 4 s per voice, each a different natural greeting line, and 1 stranger clip of 4 s (`unknown`).
  - `evaluate` results: genuine scores 0.616–0.808 (voice 1: 0.756–0.808, voice 2: 0.616–0.670); highest impostor score 0.293 (voice 1 ↔ voice 2); the stranger's best match 0.084. Separable.
  - Threshold = midpoint of the lowest genuine score (0.616) and the highest impostor score (0.293).
  - Result: 6 of 6 correct, 0 missed, 0 wrong names, the stranger kept silent.
- **Caveats:** a small sample (2 voices, 1 stranger clip). Voice 2's enrollment was about 9 dB quieter than voice 1's and scored lower. Re-check with the demo family's voices in J3.3.
- **SpeechBrain is good enough**, so no switch to Picovoice Eagle.

## Deploy

> Status: **decided** (2026-11-15).

- **Live site:** https://argos-web-bay.vercel.app. Task plan: https://argos-web-bay.vercel.app/plan.
- **Automatic.** The Vercel project `argos-web` is connected to `ogutdgn/argos` with Root Directory `web`. Every merge to `main` deploys to production, and every PR gets a preview link.
- **Manual fallback:** `vercel deploy --prod` from the **repo root** (not `web/`, because the Root Directory is already `web`). Steps: [web/README.md](../web/README.md).
- Env vars for the live site live in the Vercel project settings, not in `.env`.

## Repo structure

Folders, file layout and the station → web handoff: [structure.md](structure.md).
