# Argos web

Next.js (App Router, TypeScript) on Vercel: dashboard, invitations, magic-link form and all AI work. Root rules and docs table: [../CLAUDE.md](../CLAUDE.md). Folder layout: [../docs/structure.md](../docs/structure.md).

@AGENTS.md

## Where things go

| Path | What |
|---|---|
| `app/login/` | dashboard login |
| `app/(dashboard)/` | people, a person's memory, conversations, invitations; `layout.tsx` checks the dashboard user and has logout. Conversations read through `lib/supabase/conversations.ts` (conversations, their transcript and what was learned) |
| `app/invite/[token]/` | magic-link form for invited people |
| `app/plan/` | live task plan, read from GitHub issues |
| `app/api/` | endpoints, e.g. the station's "conversation uploaded, process it" call |
| `components/` | shared React components |
| `components/ui/` | shadcn/ui components, themed with the tokens ([../docs/design.md](../docs/design.md)) |
| `components/voice-recorder/` | the shared voice-sample recorder and its checks (`checks.ts`), used by adding the patient and by the magic-link form ([../docs/edge-cases.md](../docs/edge-cases.md), "Bad voice sample") |
| `lib/supabase/` | every database and storage call; `server.ts` for server code, `client.ts` for the browser, `admin.ts` for the server-only secret-key client (no login, bypasses RLS), `auth.ts` for login, `people.ts` for people and the patient, `memory.ts` for memory items, `storage.ts` for signed upload targets and signed URLs (server), `upload.ts` for sending a file to a signed upload URL (browser), `invitations.ts` for invitations and the magic link, `registration.ts` for saving an invited person from the magic-link form, `reminders.ts` for the reminders table and reminder audio, `proxy.ts` for the session refresh |
| `proxy.ts` | refreshes the login session; sends logged-out visitors to `/login` |
| `lib/ai/` | `provider.ts` is the only file that calls the AI provider; `reminder.ts` writes the reminder sentence; memory extraction comes in W2.2 |
| `lib/reminders/` | `hook.ts` chooses the hook (plain logic); `regenerate.ts` makes a person's next reminder. Call `after(() => regenerateReminder(personId))` whenever a person's memory changes ([../docs/tech.md](../docs/tech.md), "Reminders") |
| `lib/elevenlabs/` | `speech.ts` for the reminder voice; transcription (Scribe) comes in W2.2 |
| `lib/email/` | Resend invitations |

## Rules

- **AI provider only in `lib/ai/`.** No OpenAI (or later Google) import anywhere else, so the provider can be swapped by changing that folder.
- **Supabase only through `lib/supabase/`.** Pages and components call functions there, not `@supabase/*` directly. Tables come from `../supabase/migrations/`; never create or change them from `web/`.
- **AI and service keys stay on the server.** Only `NEXT_PUBLIC_*` values may reach the browser; everything else is read in server code only.
- **No secrets in git.** Keys live in the repo-root `.env` locally (loaded by `next.config.ts`; template `../.env.example`) and in the Vercel project settings when deployed.
- **No real personal data.** No real names, voices, photos or conversations in code, fixtures or commits; only the fictional Odyssey family.
- **Dashboard pages are private by default.** Every route needs a signed-in dashboard user (an Auth account plus a `users` row) except the ones listed in `PUBLIC_PATHS` in `proxy.ts`: `/login`, `/invite/…`, `/plan`, `/api/…`. Put new dashboard pages under `app/(dashboard)/` so its layout checks the user; Server Actions and Route Handlers check the user themselves (`requireDashboardUser()` in `lib/supabase/auth.ts`). Creating dashboard users: [README.md](README.md) ("Dashboard users").
- **UI follows [`../docs/design.md`](../docs/design.md):** Tailwind with the theme tokens only (no hex in components), shadcn components from `components/ui/`.
- **Cache Components are on** (`next.config.ts`). Request-time reads (Supabase, cookies) go inside `<Suspense>` and call `connection()` or a runtime API first.
- Run `npm run lint` and `npm run build` in `web/` before a PR.

## Env keys

Full list and which part reads each: [../docs/structure.md](../docs/structure.md) ("Env keys"). Read so far: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `NEXT_PUBLIC_SITE_URL` (base of the magic links, in `app/(dashboard)/invitations/actions.ts`), `SUPABASE_SECRET_KEY` (server only, in `lib/supabase/admin.ts`), `RESEND_API_KEY` and `RESEND_FROM_EMAIL` (server only, in `lib/email/`), `OPENAI_API_KEY` (server only, in `lib/ai/provider.ts`), `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` (server only, in `lib/elevenlabs/`), `GITHUB_TOKEN` (server only, in `app/plan/tasks.ts`). Add a key to the root `.env.example` and that list before reading it here.

## Deploy

Automatic: Vercel project `argos-web` is connected to `ogutdgn/argos` with Root Directory `web`, so every merge to `main` deploys and every PR gets a preview. Don't deploy by hand unless asked; if you must, run `vercel deploy --prod` from the repo root, not `web/`. New env vars go into the Vercel project settings too. See [../docs/tech.md](../docs/tech.md) ("Deploy").
