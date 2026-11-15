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
- **Highest score wins** (decided 2026-11-15, S1.4): the recognizer (`station/argos_station/recognizer.py`) names whoever has the highest score, if it is at or above 0.455, even when someone else is also above it. If the highest is the patient, it says nothing. No minimum gap between the top two scores.
- **Caveats:** a small sample (2 voices, 1 stranger clip). Voice 2's enrollment was about 9 dB quieter than voice 1's and scored lower. Re-check with the demo family's voices in J3.3.
- **SpeechBrain is good enough**, so no switch to Picovoice Eagle.

## Voice samples

> Status: **decided** (2026-11-15, W1.2).

- **Recorded in the browser** by one shared component, `web/components/voice-recorder/`, used by the magic-link form and by the dashboard (adding the patient). The person reads `demo/voice-script.txt` for 20–30 seconds.
- **Format:** WAV, **16 kHz, mono, 16-bit PCM**, encoded in the browser from Web Audio (about 1 MB for 30 s; the bucket limit is 10 MB). SpeechBrain reads it directly; no webm or mp4.
- **Raw microphone:** echo cancellation, noise suppression and automatic gain are turned off, so the voiceprint is built from the same kind of sound the station hears.
- **Checks before it can be accepted:** too short, too quiet, noisy. Thresholds: [edge-cases.md](edge-cases.md) ("Bad voice sample").
- **Upload:** the server makes a one-time signed upload URL for `voice-samples/{person_id}/{uuid}.wav` (`web/lib/supabase/storage.ts`), the browser uploads straight to it (`web/lib/supabase/upload.ts`), and then the server checks the file is there and sets `people.voice_sample_path`. Files never pass through a Vercel function (4.5 MB body limit). Photos use the same flow (`photos/{person_id}/{uuid}.{jpg|png|webp}`).

## Reminders

> Status: **decided** (2026-11-15, W2.1). Code: `web/lib/reminders/`, `web/lib/ai/`, `web/lib/elevenlabs/speech.ts`, `web/lib/supabase/reminders.ts`.

- **Code picks the hook, the AI only phrases it.** `lib/reminders/hook.ts` applies the order in [memory.md](memory.md) ("Choosing the conversation hook") and the never-twice rule, and the chosen item's id is saved as `reminders.hook_memory_item_id`. **gpt-5-mini** then writes one or two short sentences from name + relationship + that one item. With no hook left, the model writes name + relationship only. The model always writes the sentence because the relationship is typed freely ("I'm his son"), so it can't be pasted into a fixed template.
- **Checked before use.** The sentence must contain the visitor's first name, stay under 160 characters, and avoid corrective words ("remember", "forget", "memory", "dementia"). Otherwise it is refused.
- **Voice:** ElevenLabs text-to-speech, model `eleven_multilingual_v2`, voice `ELEVENLABS_VOICE_ID`, mp3 at 44.1 kHz / 128 kbps, uploaded to `reminder-audio/{person_id}/{reminder_id}.mp3`. The row is inserted only after the upload.
- **When:** after any change to a person's memory (a dashboard edit or delete, registration; conversation processing in W2.2), run inside Next.js `after()` so the save returns at once. The patient gets no reminder.
- **On failure** (missing keys, an AI or ElevenLabs error, a refused sentence), nothing is saved and the error is logged. The previous reminder stays current; someone with no reminder yet stays silent.
- **Leftovers:** two changes to the same person within a few seconds can both pick the same hook. Old reminder rows and their audio stay as history; the station only uses the newest. People registered before W2.1 get their first reminder on their next memory change.

## Recordings

> Status: **decided** (2026-11-15, S2.2). Code: `station/argos_station/recorder.py`. What goes into a recording: [edge-cases.md](edge-cases.md) ("What a recording holds").

- **Format:** OGG Opus (`recordings/{conversation_id}.ogg`, `audio/ogg`), **16 kHz mono**, written by libsndfile through `soundfile` (already pinned, no new dependency) as the audio comes in, so a long conversation is never held in memory.
- **Size:** libsndfile compression level **0.93**, about **24 kbps** even for loud noise (the worst case; speech and silence are smaller). A recording is capped at **4 hours**, about 44 MB, under the 50 MB bucket limit. The size is checked before the upload; a file over the limit is kept locally and not uploaded.
- **Retries:** upload and inserts **3 tries** (waits 2 s, 4 s). Processing endpoint: **5 tries** for `5xx` and network errors (waits 2, 4, 8, 16 s; 15 s timeout per try); `4xx` is logged and never retried. All three steps are idempotent (upload with upsert, inserts that ignore duplicates, and the endpoint itself).
- **Local files:** `station/data/recordings/{id}.ogg` plus a job file `{id}.json` (times, visitors, how far it got). The audio is deleted once it is in storage and the rows are in; the job file once the endpoint answered `200`/`202`, or a `4xx` (send it again by hand with `python -m argos_station.recorder --notify <id>`). Anything else is tried again from the step that failed on the next start. When the station stops, it waits up to 2 minutes for uploads in flight.

## Station start and stop

> Status: **decided** (2026-11-15, S2.3). Code: `station/argos_station/main.py`. One command from `station/`: `.venv/bin/python -m argos_station.main`.

- **Start, in order:** read `.env`; check the AirPod; load the speaker model once; one sync pass, then a voiceprint refresh; then start the recorder (it hands on what an earlier run left in `data/recordings/`), the tracker, the listener and the background sync. The station listens only after the first sync and refresh, so it starts with the newest voiceprints.
- **Staying current:** the background sync runs every **30 seconds** (`sync.SYNC_INTERVAL_SECONDS`, `--sync-interval`). After a pass that changed the people (someone added or removed, a new voice sample or reminder), the voiceprints are refreshed. The recognizer notices the new files on its own before the next clip, so no restart is needed. The recognizer and the refresh share one copy of the speaker model.
- **Missing keys:** no `SUPABASE_URL` or `SUPABASE_SECRET_KEY` → the station exits with a plain message. No `ARGOS_WEB_URL` or `STATION_API_SECRET` → a warning at start; conversations are still recorded and uploaded, and the endpoint is called on a later start once the keys are there. Supabase unreachable at start → a warning, and the station runs on what was synced before.
- **Missing devices:** no MacBook mic → the station exits (it cannot hear anyone). No AirPod → an error in the log at start, and the station keeps running silently ([edge-cases.md](edge-cases.md), "AirPod connected after the station starts").
- **Stop (Ctrl+C or SIGTERM), in order:** the listener (the mic closes, nothing new comes in), the tracker (an open conversation ends with `end_reason` "station stopped"), the recorder (waits up to 2 minutes for uploads in flight), then the background sync. A step that fails is logged and the next one still runs. The log ends with "station stopped".
- **A second Ctrl+C** quits at once. A conversation still being recorded is then lost (its audio stays in `data/recordings/` without a job file and is logged on the next start); one already recorded stays there and is handed on at the next start.
- **Test timings:** `--end-after`, `--same-within` and `--pause` shorten the tracker's rules for a live test; `--dry-run` logs which reminder would play instead of playing it. The defaults are the real rules (5 min, 30 min, 2 s).

## Magic-link registration

> Status: **decided** (2026-11-15, W1.4). Code: `web/app/invite/[token]/`, `web/lib/supabase/registration.ts`.

- **Nobody is signed in,** so the form's server actions use the secret key, and each one checks the link token again first.
- **The person's id comes from the invitation** (a version 8 UUID from a SHA-256 of the invitation id), never from the browser. Uploads go to that id's folders only, a path is accepted only under them, and a second submit for the same link hits the `people` primary key.
- **Order on submit** (no transactions through supabase-js): insert the person, insert their memory items, then use up the link with one conditional UPDATE. A failure before the last step deletes the person again, so the link can be retried and is never used up for a half-saved person. Afterwards, files left in the person's folders by earlier tries are removed.
- **Leftovers:** a form left after the uploads (never submitted) keeps its files in storage. A server stop between the insert and the last step leaves a person without a used link; a dashboard user can send a new invitation.

## Conversation processing

> Status: **decided** (2026-11-15, W2.2). Code: `web/app/api/conversations/process/route.ts`, `web/lib/processing/`, `web/lib/ai/extract.ts`, `web/lib/elevenlabs/transcribe.ts`, `web/lib/supabase/processing.ts`. The endpoint's shape: [structure.md](structure.md) ("Station → web handoff").

- **Answer first, work after.** The endpoint checks the secret, claims the conversation (`uploaded` or `failed` → `processing` in one conditional UPDATE, so two calls can't both start it), answers `202`, and does the work inside `after()` (`maxDuration` 300 s).
- **Transcription:** the recording is downloaded from `recordings` and sent to ElevenLabs Scribe (`scribe_v1`, speakers separated). Words become speaker turns, saved in `transcripts.segments` (`speaker_id`, `name`, `start`, `end`, `text`).
- **One AI call** (gpt-5-mini, strict JSON) says which speaker is the patient or each visitor, and picks at most 5 memory items ([memory.md](memory.md)). The answer is never trusted: `lib/processing/learned.ts` drops anything that breaks a rule (unknown person, first-hand item about someone who wasn't there, second-hand follow-up, bad kind, empty or over 500 characters, duplicates).
- **Speaker names:** a speaker is named only if the AI ties it to the patient or a visitor, one to one. Anyone else stays "Speaker 1", "Speaker 2". The transcript text reads "Odysseus: …" per turn.
- **Saving:** the transcript is upserted and this conversation's memory items are replaced, so a retry after a failure never saves anything twice. Then `processed`.
- **Reminders:** made again for every visitor, even when nothing new was learned (the hook that just played must not play next time), and for anyone who got a second-hand item.
- **On failure** (missing keys, Scribe or OpenAI errors, database errors): `failed` with a short `error` for the team; the station can send it again. A failing reminder never fails the conversation.
- **Leftover:** if the server stops in the middle, the conversation stays `processing` and repeat calls get `200`. Set it back to `uploaded` in Supabase to retry.

## Conversations in the dashboard

> Status: **decided** (2026-11-15, W2.3). Code: `web/app/(dashboard)/conversations/`, `web/lib/supabase/conversations.ts`.

- **List** (`/conversations`), newest first: visitors, start time, length and status ("Being processed", "Ready", "Couldn't be processed").
- **A conversation's page:** "What Argos learned" (memory items with `source_conversation_id` set), grouped by the person whose memory they went into, visitors first. Second-hand items look like the others and come last in each group, with only a small "told by …" line. Then the full transcript (`transcripts.text`). Speaker segments are not shown yet; W2.2 decides their shape.
- **Not processed yet or failed:** a calm note instead of the transcript. The `error` column is never shown.
- **Times** are shown in the viewer's own time zone (`web/components/local-time.tsx`), because the server only knows UTC.

## Deploy

> Status: **decided** (2026-11-15).

- **Live site:** https://argos-web-bay.vercel.app. Task plan: https://argos-web-bay.vercel.app/plan.
- **Automatic.** The Vercel project `argos-web` is connected to `ogutdgn/argos` with Root Directory `web`. Every merge to `main` deploys to production, and every PR gets a preview link.
- **Manual fallback:** `vercel deploy --prod` from the **repo root** (not `web/`, because the Root Directory is already `web`). Steps: [web/README.md](../web/README.md).
- Env vars for the live site live in the Vercel project settings, not in `.env`.

## Repo structure

Folders, file layout and the station → web handoff: [structure.md](structure.md).
