# Argos web

Next.js (App Router, TypeScript) on Vercel: dashboard, invitations, magic-link form and all AI work. Root rules and docs table: [../CLAUDE.md](../CLAUDE.md). Folder layout: [../docs/structure.md](../docs/structure.md).

@AGENTS.md

## Where things go

| Path | What |
|---|---|
| `app/login/` | dashboard login |
| `app/(dashboard)/` | people, a person's memory, conversations |
| `app/invite/[token]/` | magic-link form for invited people |
| `app/plan/` | live task plan, read from GitHub issues |
| `app/api/` | endpoints, e.g. the station's "conversation uploaded, process it" call |
| `components/` | shared React components |
| `lib/supabase/` | every database and storage call; `server.ts` for server code, `client.ts` for the browser |
| `lib/ai/` | reminder sentence + memory extraction |
| `lib/elevenlabs/` | transcription (Scribe) + reminder voice |
| `lib/email/` | Resend invitations |

## Rules

- **AI provider only in `lib/ai/`.** No OpenAI (or later Google) import anywhere else, so the provider can be swapped by changing that folder.
- **Supabase only through `lib/supabase/`.** Pages and components call functions there, not `@supabase/*` directly. Tables come from `../supabase/migrations/`; never create or change them from `web/`.
- **AI and service keys stay on the server.** Only `NEXT_PUBLIC_*` values may reach the browser; everything else is read in server code only.
- **No secrets in git.** Keys live in the repo-root `.env` locally (loaded by `next.config.ts`; template `../.env.example`) and in the Vercel project settings when deployed.
- **No real personal data.** No real names, voices, photos or conversations in code, fixtures or commits; only the fictional Odyssey family.
- **Cache Components are on** (`next.config.ts`). Request-time reads (Supabase, cookies) go inside `<Suspense>` and call `connection()` or a runtime API first.
- Run `npm run lint` and `npm run build` in `web/` before a PR.

## Env keys

Full list and which part reads each: [../docs/structure.md](../docs/structure.md) ("Env keys"). Read so far: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`. Add a key to the root `.env.example` and that list before reading it here.

## Deploy

Manual for now: `vercel deploy --prod` from `web/` (Vercel project `argos-web`). Not connected to GitHub yet, so a merge does not deploy by itself. See [../docs/tech.md](../docs/tech.md) ("Deploy").
