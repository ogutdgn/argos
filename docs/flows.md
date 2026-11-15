# Flows

> Status: **decided** (2026-11-14). What happens step by step, with no tech choices.
> Scope rules live in [mvp.md](mvp.md); unusual situations in [edge-cases.md](edge-cases.md).

## Dashboard

- **Users:** the patient and their closest person, two users in the MVP. Their accounts are created by hand in Supabase; there is no sign-up page.
- **Adding the patient:** the patient is not invited. A dashboard user adds the patient's profile and records the patient's voice sample from the dashboard, so the station never mistakes the patient for a visitor.
- **Built for more users:** the design must allow adding more users later (see [possible-features.md](possible-features.md)).
- **Content:** everyone in the system and the knowledge stored about each of them, plus conversation transcripts and the important things taken from them (see Flow C).
- **Invited people** do **not** get access to the dashboard.

## Flow A: Registration

1. From the dashboard, a user invites a person they want to add.
2. The invitation is sent by **email** and contains a **magic link**.
3. The link opens a form only for that person, with no account and no dashboard access. It **expires after 1 week**.
4. The person fills in:
   - name
   - relationship to the patient
   - events and other knowledge about themselves
   - a photo (shown in the dashboard)
   - a voice sample: **20–30 seconds of reading a short given text**
5. They submit. The system now has that person's initial knowledge and voice.

Updating their info after submitting is not in the MVP (see [possible-features.md](possible-features.md)).

## Flow B: Conversation

1. A known visitor starts talking to the patient.
2. After **3–5 seconds** of speech (a natural greeting), the system identifies them.
3. **Right after recognition**, the reminder plays in the patient's ear: name + relationship + one conversation hook.
4. The reminder plays **once per person per conversation**. It does not repeat.

## Flow C: After the conversation

1. The conversation **ends when the visitor's voice has not been heard for 5 minutes**.
2. The **full transcript** is saved.
3. The **important things** from it are extracted and saved into that person's memory, so the next reminder is more current.
4. The transcript and the important things are visible to the system and in the dashboard.
