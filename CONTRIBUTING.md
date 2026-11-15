# Contributing to Argos

## Branches

- Do not work on `main`. Open a separate branch for each piece of work.
- Branch names:
  - `feat/...` for a new feature.
  - `fix/...` for a bug fix.
- No commits go to `main` directly, except in special cases agreed with the team.

## Commit messages

### Subject line

Format: `<type>(<scope>): <imperative summary>`

`<type>` is one of:

| Type | When |
|---|---|
| `feat` | New user-visible feature or capability. |
| `fix` | Bug fix. The subject names the bug, not the solution. |
| `docs` | Documentation only. |
| `style` | Formatting or whitespace only. |
| `refactor` | Restructuring code without changing behaviour. |
| `ui` | Visual-only change (no logic). |
| `test` | Tests only. |
| `chore` | Tooling, dependencies, config. |

`<scope>` is one of:

- `web`: anything under `web/` (Next.js app).
- `station`: anything under `station/` (Python patient station).
- `supabase`: anything under `supabase/` (database tables, seed data).
- `docs`: anything under `docs/`.
- `skills`: anything under `.claude/`.
- `repo`: repo-root files (`README.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `.gitignore`, config), `demo/`, or cross-cutting changes.
- `restructure`: large structural changes (rare).

Do not invent other scopes. Folder layout: `docs/structure.md`.

Use the imperative form, start with a lowercase word, and keep the subject under 72 characters.

Examples:

```
docs(docs): add edge-cases.md and rename pff.md to possible-features.md
docs(repo): add README with the Odyssey story and demo family
```

### Body

Every non-trivial commit has a body. Leave one blank line after the subject, then add:

**What changed**: a bullet list of concrete changes. Name the files, sections or components touched.

```
- Add docs/edge-cases.md as an empty file to fill in together
- Rename docs/pff.md to docs/possible-features.md
- Remove the edge-case section from possible-features.md
- Update links in docs/mvp.md
```

**Why**: one or two sentences on the motivation. What problem does this solve, or what goal does it serve?

**Impact notes** (when relevant):

- `Scope impact: <what>` if the commit changes what is in or out of the MVP (`docs/mvp.md`), or moves something between MVP and `docs/possible-features.md`.
- `Breaking: <what>` if any contract between parts of the system changed.

### Trailer

Commits never contain a `Co-Authored-By` line, including AI authorship trailers.

## Staging

- Stage files explicitly by path. Never use `git add .` or `git add -A`.
- Run `git diff --cached --stat` before committing to check the staged set.
- Never commit:
  - `.env` files, API keys, passwords or other credentials.
  - **Personal data of real people:** voice samples, photos, recorded or transcribed conversations, memory entries about real family members. Only fictional demo data (the Odyssey family) may be committed.
  - Dependency and build folders (for example `node_modules/`, `.venv/`, build output), caches, agent log dumps.

## Secrets and personal information

- No personal information in code, commits or PRs: no names, email addresses, passwords or keys.
- Secrets live only in `.env`. The repo keeps an empty template in `.env.example`.

## Push and pull requests

- Push only to your own fork: `git push origin <branch>`.
- Run lint and tests before opening a PR.
- You cannot merge your own PR. Another teammate must approve it.
- Always open a PR for any change to MVP scope in `docs/mvp.md`, or anything touching 5 or more files.
- Force-push only on your own branch, never on `main`.

## Code style

- Follow the existing code style and folder structure.
- Do not change unrelated code.
- Do not lump unrelated changes into one commit.

## What not to do

- Skip hooks (`--no-verify`). Investigate the failing hook instead.
- Bypass commit signing.
- Amend a commit that has already been pushed.
