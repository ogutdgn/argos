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

## Important things from a conversation

Extracted from the transcript after a conversation ends:
- new life events
- plans and promises ("I'll bring the kids on Sunday")
- topics they talked about
- what the patient enjoyed
- what the visitor said about other registered people (goes to their memory, as second-hand)

**Never saved:** the patient's confusion or mistakes. This protects their dignity.

## Control

Dashboard users can **edit and delete** any memory item, for example to fix something extracted wrongly.
