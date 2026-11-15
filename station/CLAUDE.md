# Station

The Python patient station that runs on the MacBook. It listens, recognizes a visitor's voice, plays the ready-made reminder into the AirPod, and records and uploads the conversation. Root rules: [../CLAUDE.md](../CLAUDE.md). Tools: [../docs/tech.md](../docs/tech.md).

## Run

```bash
cd station
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m argos_station.main
```

Keys come from `station/.env` (falls back to the repo-root `.env`): `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`. Never commit `.env`.

## Where things go

- One job per module in `argos_station/`, as listed in [../docs/structure.md](../docs/structure.md): `sync`, `voiceprints`, `listener`, `recognizer`, `player`, `tracker`, `recorder`. `main.py` only wires them together.
- Dependencies go in `requirements.txt`, pinned (`==`).
- The station never calls an AI provider. Reminders are made ahead of time by the web app; the station only plays them.
- Tables in `supabase/migrations/` are the contract with the web app. Read and write them; don't change them from here.

## Rules

- **Silence over mistakes.** If unsure who is speaking, play nothing. On any error during a conversation, stay quiet and log it; never play a wrong or half-ready reminder.
- **Discreet.** Audio plays into the AirPod only, never through the MacBook speakers.
- **No real voices or recordings in git.** Voice samples, voiceprints, recordings and transcripts live in Supabase storage or in ignored local folders. Only fictional demo material goes in `demo/`.
