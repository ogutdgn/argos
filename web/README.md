# Argos web

The Next.js app: dashboard, invitations, magic-link form and all AI work. Agent rules: [CLAUDE.md](CLAUDE.md).

## See the app

Live at https://argos-web-bay.vercel.app. It opens the dashboard login; sign in with a dashboard user (see "Dashboard users").

## Run locally (developers)

Copy the repo-root `.env.example` to `.env` (in the repo root, not in `web/`) and fill in at least `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` (Supabase: Project Settings → API Keys, the publishable key); `next.config.ts` loads it. Then in `web/`: `npm install` and `npm run dev`.

The task plan is live at https://argos-web-bay.vercel.app/plan (not linked from the app). Locally it is at `/plan` too and needs `GITHUB_TOKEN` in `.env`: a fine-grained token with read-only access to public repositories is enough.

## Dashboard users

Dashboard login is email + password through Supabase Auth. There is no sign-up page: each dashboard user is created by hand and needs **both** a Supabase Auth account and a row in the `users` table with the same id. An account without that row cannot sign in (the login page says "no dashboard access").

For the demo, create two users: the patient **Laertes** and his closest person **Odysseus**. In the Supabase dashboard for the project:

1. **Turn off public sign-ups (once):** Authentication → Sign In / Providers → turn off **Allow new users to sign up** → Save.
2. **Create the account:** Authentication → Users → **Add user** → **Create new user**. Enter an email you can reach and a password you choose, keep **Auto Confirm User** ticked, then **Create user**.
3. **Copy its id:** click the new user and copy the **User UID**.
4. **Add the `users` row:** SQL Editor → run (with the UID from step 3):

   ```sql
   insert into public.users (id, name) values ('<User UID>', 'Laertes');
   ```

5. Repeat steps 2–4 for `Odysseus`.
6. Check: open `/login`, sign in, and you land on the dashboard with the name in the header. **Log out** goes back to `/login`.

More users later: the same steps. Removing someone: delete their Auth user (the `users` row goes with it).

## Deploy

Automatic: the Vercel project (`argos-web`) is connected to `ogutdgn/argos` with **Root Directory = `web`**. Every merge to `main` deploys to https://argos-web-bay.vercel.app, and every PR gets a preview link.

Manual fallback, only if needed: `vercel login`, then `vercel link` in the **repo root** (pick `argos-web`), then from the repo root on an up-to-date `main`:

```bash
vercel deploy --prod
```

Run it from the repo root, not `web/`: the Root Directory is already `web`.

Env vars for the deployed site are set in the Vercel project settings (`vercel env add <NAME> production`), not read from `.env`.
