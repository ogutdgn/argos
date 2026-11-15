# Argos web

The Next.js app: dashboard, invitations, magic-link form and all AI work. Agent rules: [CLAUDE.md](CLAUDE.md).

## Run locally

1. Create `web/.env.local` with `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` (from the Supabase project: Project Settings → API).
2. In `web/`:

```bash
npm install
npm run dev
```

3. Open http://localhost:3000. The page says whether it can read from Supabase.

## Deploy

Vercel project with **Root Directory** set to `web`, and the same two env vars set in the Vercel project settings.
