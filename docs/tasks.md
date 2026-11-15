# Tasks

> Status: **decided** (2026-11-14). The MVP from [mvp.md](mvp.md), split into tasks two people can work on at the same time.
> Tools: [tech.md](tech.md). Folders: [structure.md](structure.md).

## How this works

- **Two tracks:** **Web** (`web/`) and **Station** (`station/`). Each person takes one track, so you rarely touch the same files. **Joint** tasks are done together.
- **Phases:** a task can start once every task in its **Depends on** list is merged. Tasks in the same phase on different tracks run in parallel.
- **One task = one branch = one PR.**
  - Branch: the name given in the task, always `feat/<task-id>-<short-name>`.
  - PR title starts with the task ID, for example `W1.3: invitations`.
  - PR description says `Closes #<issue number>`, so the task's issue closes when the PR is merged.
- **Status lives in GitHub Issues**, not in this file. Each task has one issue with the task ID in its title. Assign the issue to yourself when you start; it closes when its PR is merged. This file only defines the tasks.
- **Who takes what** is decided by the team, through issue assignees.
- **Not blocked by the other track:** use fake data until the real thing is merged. The station can play a sample audio file before reminders exist; the web app can process a sample recording before the station uploads real ones.
- **Contract changes** (`supabase/migrations/`, the processing endpoint): talk first, then change them in their own PR.

## Overview

| Phase | Web | Station | Joint |
|---|---|---|---|
| 0. Foundation | W0.1 → W0.2 | S0.1, S0.2 | J0.1 |
| 1. Core pieces | W1.1 → W1.2, W1.3 → W1.4 | S1.1 → S1.2, S1.3 → S1.4, S1.5 | |
| 2. AI and conversations | W2.1, W2.2, W2.3 | S2.1, S2.2 → S2.3 | |
| 3. Together and demo | | | J3.1 → J3.2 → J3.3, J3.4 |

---

## Phase 0: Foundation

### J0.1 Contract: database and processing endpoint
- **Track:** Joint · **Depends on:** — · **Branch:** `feat/j0-1-contract`
- **What:**
  - Create the Supabase project.
  - Write the tables in `supabase/migrations/`: users, people (incl. the patient), memory items, invitations, conversations, transcripts, reminders. Follow [memory.md](memory.md) and [flows.md](flows.md).
  - Create storage buckets: photos, voice samples, recordings, reminder audio.
  - Agree on the processing endpoint the station calls after uploading a recording: URL, request, response, and a shared secret so only the station can call it.
  - Add the keys needed by both parts to `.env.example` (empty values), and a root `.gitignore` that keeps out `.env`, dependency and build folders, and any audio, photo or recording files.
- **Done when:** the migrations apply to the Supabase project, the buckets exist, and the endpoint shape is written down in `docs/structure.md`.

### W0.1 Web skeleton
- **Track:** Web · **Depends on:** — · **Branch:** `feat/w0-1-web-skeleton`
- **What:** Next.js app in `web/` with the folders from [structure.md](structure.md), Supabase client in `web/lib/supabase/`, `web/CLAUDE.md`, deployed to Vercel.
- **Done when:** an empty page is live on Vercel and can read from Supabase.

### W0.2 Plan page
- **Track:** Web · **Depends on:** W0.1 · **Branch:** `feat/w0-2-plan-page`
- **What:** a `/plan` page in the web app that reads the task issues from GitHub (server-side, with a GitHub token stored only in Vercel) and shows them as a swimlane: rows Web, Station, Joint; columns phases 0–3. Each task shows its state (done = closed, in progress = assigned, ready = all dependencies closed, blocked = otherwise), its assignee, and links to its issue. Not linked from the rest of the app, and nothing about real people is shown.
- **Done when:** closing or assigning an issue on GitHub changes the page on the next reload, with no manual update.

### S0.1 Station skeleton
- **Track:** Station · **Depends on:** — · **Branch:** `feat/s0-1-station-skeleton`
- **What:** Python project in `station/` with the files from [structure.md](structure.md) (empty), `requirements.txt`, `station/CLAUDE.md`, Supabase client.
- **Done when:** `main.py` runs on the MacBook and can read from Supabase.

### S0.2 Voice recognition test
- **Track:** Station · **Depends on:** — · **Branch:** `feat/s0-2-voice-test`
- **What:** `station/scripts/voice_test.py` and `demo/voice-script.txt`, as described in [tech.md](tech.md): register 3 real voices with SpeechBrain, then test 3–5 second greetings. Real voice files stay out of git.
- **Runs alongside S0.1:** keep its dependencies in its own `station/scripts/requirements-voice-test.txt`, not in `station/requirements.txt`, so the two branches don't conflict. S1.2 later moves SpeechBrain into the main file.
- **Done when:** greetings are matched to the right person, an unknown voice is not matched, and the confidence threshold is written down. If SpeechBrain is not good enough, the result says so and we switch to Picovoice Eagle.

---

## Phase 1: Core pieces

### W1.1 Dashboard login
- **Track:** Web · **Depends on:** W0.1, J0.1 · **Branch:** `feat/w1-1-login`
- **What:** Supabase login for dashboard users (patient and closest person), built so more users can be added later. The two accounts are created by hand in Supabase; no sign-up page.
- **Done when:** both demo users can log in, and logged-out visitors cannot see the dashboard.

### W1.2 People and memory in the dashboard
- **Track:** Web · **Depends on:** W1.1 · **Branch:** `feat/w1-2-people`
- **What:** list of everyone in the system; a person's page with profile, photo and memory items; edit and delete memory items. Add the patient: profile plus a voice sample recorded from the dashboard (same recorder and checks as W1.4).
- **Done when:** a dashboard user can see every person, edit or delete any memory item, and add the patient with a voice sample.

### W1.3 Invitations
- **Track:** Web · **Depends on:** W1.1 · **Branch:** `feat/w1-3-invitations`
- **What:** invite a person from the dashboard; email with a one-time magic link through Resend; link expires after 1 week; send a new invitation when one expired.
- **Done when:** an invited person receives the email, the link works once, and an expired link is refused.

### W1.4 Magic-link form
- **Track:** Web · **Depends on:** W1.3 · **Branch:** `feat/w1-4-invite-form`
- **What:** the form at `invite/[token]`: name, relationship, events and knowledge, photo, voice sample (20–30 seconds reading `demo/voice-script.txt`). Ask to record again if the sample is too short, too quiet or noisy.
- **Done when:** a submitted form creates the person, their memory items, and their photo and voice sample in storage.

### S1.1 Sync
- **Track:** Station · **Depends on:** S0.1, J0.1 · **Branch:** `feat/s1-1-sync`
- **What:** `sync.py` regularly pulls people, voice samples and reminder audio from Supabase to the Mac.
- **Done when:** a person added in Supabase appears on the Mac within a minute, with their files.

### S1.2 Voiceprints
- **Track:** Station · **Depends on:** S1.1, S0.2 · **Branch:** `feat/s1-2-voiceprints`
- **What:** `voiceprints.py` turns each voice sample into a voiceprint, using what S0.2 learned, and moves SpeechBrain into `station/requirements.txt`. The patient's own voice is marked so it is never matched as a visitor.
- **Done when:** every synced person has a voiceprint, including the patient.

### S1.3 Listener
- **Track:** Station · **Depends on:** S0.1 · **Branch:** `feat/s1-3-listener`
- **What:** `listener.py` listens through the MacBook mic (not the AirPod mic) and detects speech with Silero VAD.
- **Done when:** it reliably reports when someone starts and stops speaking, and hands over the first 3–5 seconds of speech.

### S1.4 Recognizer
- **Track:** Station · **Depends on:** S1.2, S1.3 · **Branch:** `feat/s1-4-recognizer`
- **What:** `recognizer.py` compares speech against voiceprints with the threshold from S0.2. If not confident, it returns "unknown".
- **Done when:** the recognition, unsure-match and unknown-voice rules in [edge-cases.md](edge-cases.md) hold in a live test.

### S1.5 Player
- **Track:** Station · **Depends on:** S0.1 · **Branch:** `feat/s1-5-player`
- **What:** `player.py` plays a reminder audio file into the AirPod only.
- **Done when:** a sample audio file plays in the AirPod and not through the MacBook speakers.

---

## Phase 2: AI and conversations

### W2.1 Reminders
- **Track:** Web · **Depends on:** W1.2 · **Branch:** `feat/w2-1-reminders`
- **What:** `web/lib/ai/` writes each person's one-sentence reminder (name + relationship + one hook, chosen by the rules in [memory.md](memory.md)); `web/lib/elevenlabs/` turns it into audio; both are saved. Regenerated whenever that person's memory changes.
- **Done when:** adding or editing a memory item produces a new reminder sentence and audio, and the same hook is never used twice in a row.

### W2.2 Conversation processing
- **Track:** Web · **Depends on:** J0.1, W2.1 · **Branch:** `feat/w2-2-processing`
- **What:** the processing endpoint from J0.1: transcribe the recording with ElevenLabs Scribe, save the transcript, extract the important things (including second-hand info about other registered people), save them, regenerate reminders.
- **Done when:** calling the endpoint with a sample recording saves a transcript, adds memory items, and updates the reminder.

### W2.3 Conversations in the dashboard
- **Track:** Web · **Depends on:** W1.2 · **Branch:** `feat/w2-3-conversations`
- **What:** show each conversation's transcript and the important things taken from it. Second-hand info does not stand out.
- **Done when:** a processed conversation is visible in the dashboard.

### S2.1 Conversation tracker
- **Track:** Station · **Depends on:** S1.4, S1.5 · **Branch:** `feat/s2-1-tracker`
- **What:** `tracker.py`: starts a conversation when a known visitor is recognized and plays their reminder once; ends it after 5 minutes without their voice; treats a return within 30 minutes as the same conversation; handles two visitors at once.
- **Done when:** the conversation rules in [flows.md](flows.md) and [edge-cases.md](edge-cases.md) hold in a live test.

### S2.2 Recorder and uploader
- **Track:** Station · **Depends on:** S2.1, J0.1 · **Branch:** `feat/s2-2-recorder`
- **What:** `recorder.py` records the conversation, uploads it to Supabase when it ends, then calls the processing endpoint. Unknown-voice conversations are not saved.
- **Done when:** a finished conversation appears in Supabase storage and the endpoint is called.

### S2.3 Station wiring
- **Track:** Station · **Depends on:** S1.1, S2.2 · **Branch:** `feat/s2-3-main`
- **What:** `main.py` runs sync, listener, recognizer, tracker, player and recorder together.
- **Done when:** one command starts the station and it runs a full conversation without help.

---

## Phase 3: Together and demo

### J3.1 Demo data
- **Track:** Joint · **Depends on:** W1.4, S1.2 · **Branch:** `feat/j3-1-demo-data`
- **What:** `supabase/seed.sql` with the Odyssey family (Laertes, Odysseus, Telemachus, Penelope), memory items and the two dashboard users. The demo voices are recorded through the real form, not committed.
- **Done when:** a fresh database can be filled with the demo family in one step.

### J3.2 End-to-end test
- **Track:** Joint · **Depends on:** all Phase 2 tasks, J3.1 · **Branch:** `feat/j3-2-e2e`
- **What:** run the full loop: invite → form → visitor speaks → reminder in the AirPod → conversation ends → memory updated → next reminder is different.
- **Done when:** the "Done when" in [mvp.md](mvp.md) holds: a family member speaks and the patient hears the right reminder within a few seconds. Bugs found here become `fix/...` branches.

### J3.3 Edge-case pass
- **Track:** Joint · **Depends on:** J3.2 · **Branch:** `fix/j3-3-edge-cases`
- **What:** go through every case in [edge-cases.md](edge-cases.md) and check it live.
- **Done when:** every case behaves as decided, or the gap is written down.

### J3.4 Demo rehearsal
- **Track:** Joint · **Depends on:** J3.2 · **Branch:** `feat/j3-4-demo`
- **What:** the demo script, a checklist (mic input, AirPod output, keys, internet), and backup recordings in case the room is noisy.
- **Done when:** two full rehearsals run without problems.
