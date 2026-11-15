# Argos web

The Next.js app: dashboard, invitations, magic-link form and all AI work. Agent rules: [CLAUDE.md](CLAUDE.md).

## See the app

Live at https://argos-web-bay.vercel.app. The page says whether it can read from Supabase.

## Run locally (developers)

Copy the repo-root `.env.example` to `.env` (in the repo root, not in `web/`) and fill in at least `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` (Supabase: Project Settings → API Keys, the publishable key); `next.config.ts` loads it. Then in `web/`: `npm install` and `npm run dev`.

## Deploy

For now, deploys to https://argos-web-bay.vercel.app are manual with the Vercel CLI. The Vercel project (`argos-web`) is not connected to GitHub yet, so merging to `main` does **not** update the live site.

1. Once: `vercel login`, then `vercel link` in `web/` and pick the `argos-web` project.
2. Each time: switch to an up-to-date `main`, then in `web/`:

```bash
vercel deploy --prod
```

Env vars for the deployed site are set in the Vercel project settings (`vercel env add <NAME> production`), not read from `.env`.

Later, for automatic deploys: the repo owner (`ogutdgn`) installs the Vercel GitHub app on `ogutdgn/argos`, then the Vercel project is connected to it (`vercel git connect`) with **Root Directory = `web`**.
