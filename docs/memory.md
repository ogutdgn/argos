# Memory

> Status: **decided** (2026-11-14). What we store and how the conversation hook is chosen, with no tech choices.
> How memory is filled and updated step by step: [flows.md](flows.md).

## Memory per person

Every item has a **date**.

| Type | What | Comes from |
|---|---|---|
| Profile | Name, relationship, photo, voice | Registration |
| Facts | Stable things ("lives in Sparta", "has two kids") | Registration, conversations |
| Shared memories | Old moments with the patient ("the fruit trees") | Registration, conversations |
| Recent events | Time-sensitive news ("just came back from Sparta") | Registration, conversations |
| Conversation history | Full transcripts + the important things taken from them | Conversations |

- **Recent events go stale:** they count as "recent" for **30 days**, then become plain facts.
- **From registration:** the magic-link form has three boxes, one item per line: "About your life" (facts), "Memories you share" (shared memories) and "Recent news" (recent events). They are first-hand and dated the day the person registers. At least one item is needed, so there is always a hook.

## Information about other people

- When a visitor mentions another registered person ("Dad got a new job"), it is also saved into **that** person's memory.
- It is marked as **second-hand**: who said it, and when.
- It stays in the background: it has **lower priority** than what the person said themselves, and does not stand out in the dashboard.

## Choosing the conversation hook

Priority, highest first:
1. A follow-up from the last conversation ("Last time you talked about his trip").
2. A recent event.
3. A shared memory.

**Never the same hook twice in a row.**

When none of those is left (decided 2026-11-15, W2.1):
4. An older follow-up (from an earlier conversation).
5. A fact.
6. Nothing: the reminder is name + relationship only ("Odysseus, your son.").

Within each step, what the person said themselves comes before second-hand items, then the newest first. "The last conversation" is the latest conversation that left any follow-ups.

## Important things from a conversation

Extracted from the transcript after a conversation ends:
- new life events
- plans and promises ("I'll bring the kids on Sunday")
- topics they talked about
- what the patient enjoyed
- what the visitor said about other registered people (goes to their memory, as second-hand)

**Never saved:** the patient's confusion or mistakes. This protects their dignity.

How they are stored (decided 2026-11-15, W2.2):
- **At most 5 items per conversation,** the most important first, so each person's memory stays short and easy to check.
- Plans, promises, topics and what the patient enjoyed are **follow-ups** in the visitor's own memory. New events are **recent events**, stable things **facts**, old moments with the patient **shared memories**.
- What a visitor says about another registered person (the patient included) goes into that person's memory as second-hand, as a recent event or a fact. Follow-ups are never second-hand.
- Items are dated the day the conversation ended.

## Control

Dashboard users can **edit and delete** any memory item, for example to fix something extracted wrongly.
