# Argos

Voice companion for people living with dementia: it recognizes a visitor by voice and whispers into the patient's ear who they are, plus one thing to talk about. Background and story: [README.md](README.md).

## Outline

- **Goal:** keep the patient comfortable and relaxed in conversations.
- **Core loop:** memory → recognize the voice → reminder in the ear → patient continues → memory updated after the conversation ends.
- **Principles:** discreet, never corrective, silence over mistakes.
- **Demo family:** patient Laertes; visitors Odysseus (son), Telemachus (grandson), Penelope (daughter-in-law).

## Docs

| File | Read it when |
|---|---|
| [docs/mvp.md](docs/mvp.md) | Always. The source of truth for scope. |
| [docs/flows.md](docs/flows.md) | Building any user-facing step: registration, conversation, after the conversation. |
| [docs/memory.md](docs/memory.md) | Storing, updating or reading memory, or choosing the conversation hook. |
| [docs/possible-features.md](docs/possible-features.md) | Something seems out of MVP scope. |
| [docs/edge-cases.md](docs/edge-cases.md) | Handling unusual or failure situations. |

## Rules

- Only build what is in `docs/mvp.md`. Anything else is out of scope until it is moved there.
- The plan (tech stack, architecture, tasks) is being decided together with the team. Do not invent or add it; propose and ask first.
- New decisions go into the matching doc, not only into chat.
- Before any git commit, follow the `commit-style` skill ([.claude/skills/commit-style/SKILL.md](.claude/skills/commit-style/SKILL.md)).
