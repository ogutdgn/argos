# MVP

> Status: **decided** (2026-11-14).
> This is the source of truth for what is in scope. Anything not listed here is out of scope; see [possible-features.md](possible-features.md) for possible future features and [edge-cases.md](edge-cases.md) for edge cases.

## Goal

Keep the person with Alzheimer's comfortable and relaxed during conversations. They can feel bad when they can't keep up with a conversation, so we quietly remind them who they are talking to and what to talk about.

## Core loop

1. **Memory:** each person close to the patient has a memory: who they are, their relationship to the patient, past chats, events.
2. **Recognize:** when that person speaks, we identify them by their voice.
3. **Remind:** the patient hears a short reminder in their ear.
4. **Continue:** the patient carries on the conversation.
5. **Update:** when the conversation ends, that person's memory is updated.

## Scope

| Part | MVP |
|---|---|
| Initial memory | Family members add themselves: who they are, relationship to the patient, initial knowledge, voice sample. |
| Live memory update | Once, after the conversation ends, the conversation updates that person's memory. |
| Recognition | Automatic, when a known voice is heard. |
| Patient's own voice | Never mistaken for a visitor. |
| Reminder delivery | In the ear only. |
| Reminder content | One short sentence: name + relationship + one conversation hook. |

## Principles

- **Discreet:** only the patient hears the reminder.
- **Never corrective:** no "don't you remember…" style wording; only gentle hints.
- **Silence over mistakes:** if we are not sure who is speaking, say nothing. Naming the wrong person is worse than naming no one.

## Done when

A family member speaks, and the patient hears the right reminder in their ear within a few seconds.
