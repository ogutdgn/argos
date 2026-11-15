# Possible future features

> Not in the MVP. Do not build these unless they are moved into [mvp.md](mvp.md).
> Edge cases live separately in [edge-cases.md](edge-cases.md).

## Phone calls in memory

Keep phone calls between the patient and family members in memory, as well as face-to-face conversations. No reminders during calls: only the transcript is kept.

**Why it can come later:** a call transcript goes into the same memory as a face-to-face conversation and runs the same update as Flow C in [flows.md](flows.md). Adding it should not change the rest of the system much.

**Options discussed (2026-11-14), not decided:**

| Option | How | Pros | Cons |
|---|---|---|---|
| Argos phone number (e.g. Twilio) | Family calls an Argos number, which forwards to the patient's phone and records each side on its own channel. Transcript from Twilio or our own speech-to-text. | Fastest for real phone calls. Caller's number identifies the person, so no voice recognition is needed. Clean "who said what". Consent message at call start. | Third-party service and cost. Family must use the new number; the patient's outgoing calls must go through it too. |
| Calls through Argos (WebRTC) | Family calls the patient from Argos in the browser; the patient's device with Argos rings. | We own everything: no phone number, no third party, separate audio per person, more private. | Not real phone calls. The patient's device must be on and ready. |
| Own phone system (e.g. Asterisk) | We run the phone server and only rent the connection to the phone network. | Full control over recording and transcription. | Days of setup. |
| Phone on speaker | The device that listens to face-to-face conversations also hears the call. | Almost nothing new to build. | Worse audio; the patient must use speaker; conflicts with the speakerphone edge case in [edge-cases.md](edge-cases.md). |

**Notes:**
- Chert (FaceTime agents, HackUTA sponsor) was considered and dropped: its track rewards using video, and its agent must join the call as a participant.
- Recording calls can need consent from both sides depending on the place; a short message at the start of the call covers it.
- Apps cannot record calls on iPhone; the built-in call recording is manual.

## Face

Use the face, as well as the voice. Exact meaning (recognizing faces vs. showing something visual) to be decided.

## Dashboard access for close people

Give close friends and family strict, limited access to the dashboard, beyond the patient and their closest person. With it they could:
- update important things happening in their life
- send pictures of themselves to help the patient remember them

This would replace the one-time magic link with a dashboard account with strict access, and would also let people update their info after registering.

## Memory about the patient

Keep a small memory of things the patient says about themselves in conversations ("I miss my garden"). How it would be used (dashboard, reminder, or both) is to be decided.

## SMS invitations

Send the magic-link invitation by SMS as well as email.

## Hear the reminder again

The patient can ask to hear the reminder again during a conversation (for example by tapping the earbud), when they lose track of who they are talking to.

## Never-mention topics

Dashboard users mark topics the system must never bring up (for example a family member who passed away, or a divorce), so a hook never upsets the patient.

## New people

Add and recognize people who were not registered in advance.
