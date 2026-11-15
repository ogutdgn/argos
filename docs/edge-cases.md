# Edge cases

> Status: **decided** (2026-11-14) for the cases below. Add new ones as we find them.
> Built on the MVP principles in [mvp.md](mvp.md): discreet, never corrective, silence over mistakes.
> Flows referenced here: [flows.md](flows.md).

## Recognition

### Unknown voice
Someone who is not registered speaks.
**Decision:** say nothing, and do not save that conversation.

### Unsure match
The system thinks it might be a registered person, but is not confident.
**Decision:** say nothing. No "I think this is…" reminders in the MVP.

### Voice sounds different
A registered visitor sounds different (for example, they have a cold).
**Decision:** same as an unsure match. If the system is not confident, it stays silent.

### Two visitors at once
Two registered visitors arrive together (for example Odysseus and Penelope).
**Decision:** one reminder for each, one after the other with a short pause. Each still plays only once per conversation.
The pause is **2 seconds** of silence after the first reminder ends (decided 2026-11-15, S2.1). A visitor heard while a conversation is going on joins it and gets their own reminder the same way.

## Conversation

### Visitor leaves for a short time
The visitor steps out (for example to the restroom) for around 10 minutes. By Flow C, the conversation ends after 5 minutes without their voice.
**Decision:** if they come back within **30 minutes**, it is the same conversation. No new reminder, and the memory update waits until they really leave.

How the station applies it (decided 2026-11-15, S2.1, `station/argos_station/tracker.py`):
- **The clock starts when they were last heard.** After **5 minutes** without any of the conversation's visitors, they count as away. If one of them is heard again within **30 minutes** of when they were last heard, it is the same conversation.
- **The conversation ends 30 minutes after the visitors were last heard**, and only then is it handed on (recording, memory update). Its end time (`ended_at`) is when they were last heard, not when the station noticed.
- **Someone new while the others are away** (for example Telemachus arrives after Odysseus left 10 minutes ago): the old conversation ends there, and a new one starts with its own reminder.
- **Only a recognized visitor counts as heard.** The patient's voice, unknown voices and speech too short to recognize (under 3 s) do not keep a conversation going.

### What a recording holds
Only conversations the tracker opened (a recognized visitor) are recorded, so a conversation with only unknown voices is never recorded or saved.
**Decision (2026-11-15, S2.2, `station/argos_station/recorder.py`):**
- **The greeting is kept.** The station holds the last **10 seconds** of mic audio in memory only. When a conversation starts, they go first into the recording, so the 3–5 s greeting that led to the recognition is in it. Older audio is dropped and never written anywhere.
- **The away gap is cut out.** When the visitors count as away (5 minutes not heard), the recording pauses. If one of them comes back within 30 minutes, it goes on, again starting with the 10 seconds before the return. What the room heard in between is not kept.
- **The end.** A conversation that ended because nobody came back stopped recording when it went away, so the recording ends about 5 minutes after the visitors were last heard (the goodbye is in it). `conversations.started_at` and `ended_at` stay the tracker's times (first recognized, last heard).
- **Station stopped.** A conversation open when the station is stopped (`end_reason` "station stopped") is uploaded like any other.
- **At most 4 hours** per recording; past that nothing more is written and the first 4 hours are uploaded.

### Patient forgets mid-conversation
The patient got the reminder, but loses track later in the same conversation.
**Decision:** in the MVP the reminder does not repeat. A "hear it again" option is a possible feature ([possible-features.md](possible-features.md)).

### Voices from a TV, radio or speakerphone
**Decision:** ignored in the MVP. Phone calls are a possible feature.

## Station

### AirPod not connected
The AirPod is off, out of range, or not paired when a reminder should play.
**Decision:** play nothing and log it. Never fall back to the MacBook speakers.
The same goes for a visitor whose reminder audio has not synced yet. There is one try per visitor per conversation (decided 2026-11-15, S2.1): a reminder that did not play is not tried again later in that conversation, so it never interrupts the talk late.

### AirPod connected after the station starts
The station only sees the audio devices that were there when it started (`station/argos_station/player.py`). Re-reading them would restart the audio system and break the listener's mic stream.
**Decision (found 2026-11-15, S1.5):** until the station is restarted, an AirPod connected later is treated as not connected, so reminders stay silent. Connect the AirPod before starting the station; this goes on the demo checklist (J3.4).
At start the station checks for the AirPod and logs it clearly if it is not there (decided 2026-11-15, S2.3, `station/argos_station/main.py`). It keeps running silently; to get reminders, connect the AirPod and restart it.

### Recording or upload fails
The recording breaks, or Supabase or the web app cannot be reached when a conversation ends.
**Decision (2026-11-15, S2.2):** nothing plays and the station keeps running; it is logged. A broken recording is not uploaded. The steps run in order (upload, then the rows, then the processing endpoint), and a row is never inserted for a file that did not upload. What did not finish stays in `station/data/recordings/` and is tried again from the step that failed when the station next starts. Numbers: [tech.md](tech.md) ("Recordings").

## Registration and memory

### Expired magic link
The person did not fill in the form within 1 week.
**Decision:** a dashboard user can send a new invitation.

### Bad voice sample
The sample is too short, too quiet, or noisy.
**Decision:** the form asks them to record again before they can submit.

The same recorder and checks are used by the magic-link form and by the dashboard when adding the patient (`web/components/voice-recorder/`, numbers in `checks.ts`). The checks run in the browser on the 16 kHz recording, cut into 30 ms frames:

| Check | Fails when | What the person is asked |
|---|---|---|
| Too short | under **20 s** recorded, or under **10 s** of speech in it (frames within 20 dB of the speech level and at least 10 dB above the background) | to read the whole text once more, at an easy pace |
| Too quiet | speech level (95th percentile of frame loudness) below **−40 dBFS** | to move a little closer to the microphone |
| Noisy | speech level less than **15 dB** above the background (10th percentile of frame loudness) | to find a quieter spot |

Recording stops on its own at **30 s**. The wording stays warm and never says what went wrong with the person. Format: [tech.md](tech.md) ("Voice samples").

### Nothing new in the conversation
The conversation was only small talk.
**Decision:** save the transcript, add no memory items.
