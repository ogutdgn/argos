---
name: commit-style
description: Use before any git commit in argos. Defines subject-line scope tags, body detail requirements, staging discipline (including never committing personal voice/photo/conversation data), and PR-vs-direct-commit guidance.
---

# Commit Style

## Subject line

Format: `<type>(<scope>): <imperative summary>`

`<scope>` is one of:
- `docs` — anything under `docs/` (`mvp.md`, `possible-features.md`, `edge-cases.md`).
- `skills` — anything under `.claude/`.
- `repo` — repo-root files (`README.md`, `CLAUDE.md`, `.gitignore`, config) or cross-cutting changes.
- `restructure` — large structural changes (rare).

Code scopes (for example one per app area) are added here once the project structure is decided. Until then, do not invent new scopes.

`<type>` is one of:
- `feat` — new user-visible feature or capability.
- `fix` — bug fix (subject names the bug, not the solution).
- `refactor` — internal restructure with no behaviour change.
- `ui` — visual-only change (no logic).
- `docs` — documentation only.
- `test` — tests only.
- `chore` — tooling, deps, config.

Imperative form, lowercase first word. Keep under 72 chars.

Examples:
```
docs(docs): add edge-cases.md and rename pff.md to possible-features.md
docs(repo): add README with the Odyssey story and demo family
```

## Body — required for all non-trivial commits

Always include a body. One blank line after the subject, then:

**What changed** — bullet list of concrete changes. Be specific: name the files, sections, or components touched. Example:
```
- Add docs/edge-cases.md as an empty file to fill in together
- Rename docs/pff.md to docs/possible-features.md
- Remove the edge-case section from possible-features.md
- Update links in docs/mvp.md
```

**Why** — one or two sentences explaining the motivation. What problem does this solve, or what goal does it serve?

**Impact notes** (include when relevant):
- `Scope impact: <what>` — if the commit changes what is in or out of the MVP (`docs/mvp.md`), or moves something between MVP and `docs/possible-features.md`.
- `Breaking: <what>` — if any contract between parts of the system changed.

## Trailer

**Do NOT add `Co-Authored-By: Claude` or any AI authorship trailer.** Never.

## Staging

- Stage files explicitly by path — never `git add .` or `git add -A`.
- Run `git diff --cached --stat` before committing to verify the staged set.
- Never commit:
  - `.env`, API keys, credentials.
  - **Personal data of real people:** voice samples, photos, recorded or transcribed conversations, memory entries about real family members. Only fictional demo data (the Odyssey family) may be committed.
  - Dependency and build folders (for example `node_modules/`, `.venv/`, build output), caches, agent log dumps.

## When to PR vs commit direct to branch

- **Direct commit**: single-concern change, already reviewed in conversation.
- **PR**: any change to MVP scope in `docs/mvp.md`, or anything touching 5+ files — create a PR so the team can review it before merging to main.
- Force-push only on your own branch, never on main.

## What NOT to do

- Skip hooks (`--no-verify`) — investigate the failing hook.
- Bypass signing.
- Amend a published commit.
- Lump unrelated changes into one commit.
