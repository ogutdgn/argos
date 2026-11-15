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

## Conversation

### Visitor leaves for a short time
The visitor steps out (for example to the restroom) for around 10 minutes. By Flow C, the conversation ends after 5 minutes without their voice.
**Decision:** if they come back within **30 minutes**, it is the same conversation. No new reminder, and the memory update waits until they really leave.

### Patient forgets mid-conversation
The patient got the reminder, but loses track later in the same conversation.
**Decision:** in the MVP the reminder does not repeat. A "hear it again" option is a possible feature ([possible-features.md](possible-features.md)).

### Voices from a TV, radio or speakerphone
**Decision:** ignored in the MVP. Phone calls are a possible feature.

## Registration and memory

### Expired magic link
The person did not fill in the form within 1 week.
**Decision:** a dashboard user can send a new invitation.

### Bad voice sample
The sample is too short, too quiet, or noisy.
**Decision:** the form asks them to record again before they can submit.

### Nothing new in the conversation
The conversation was only small talk.
**Decision:** save the transcript, add no memory items.
