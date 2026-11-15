# Argos web

The Next.js app: dashboard, invitations, magic-link form and all AI work. Agent rules: [CLAUDE.md](CLAUDE.md).

## See the app

Live at https://argos-web-bay.vercel.app. The page says whether it can read from Supabase.

## Run locally (developers)

Copy the repo-root `.env.example` to `.env` (in the repo root, not in `web/`) and fill in at least `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` (Supabase: Project Settings → API Keys, the publishable key); `next.config.ts` loads it. Then in `web/`: `npm install` and `npm run dev`.

The task plan is live at https://argos-web-bay.vercel.app/plan (not linked from the app). Locally it is at `/plan` too and needs `GITHUB_TOKEN` in `.env`: a fine-grained token with read-only access to public repositories is enough.

## Deploy

Automatic: the Vercel project (`argos-web`) is connected to `ogutdgn/argos` with **Root Directory = `web`**. Every merge to `main` deploys to https://argos-web-bay.vercel.app, and every PR gets a preview link.

Manual fallback, only if needed: `vercel login`, then `vercel link` in the **repo root** (pick `argos-web`), then from the repo root on an up-to-date `main`:

```bash
vercel deploy --prod
```

Run it from the repo root, not `web/`: the Root Directory is already `web`.

Env vars for the deployed site are set in the Vercel project settings (`vercel env add <NAME> production`), not read from `.env`.
