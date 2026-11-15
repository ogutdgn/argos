# Station

The Python patient station that runs on the MacBook. It listens, recognizes a visitor's voice, plays the ready-made reminder into the AirPod, and records and uploads the conversation. Root rules: [../CLAUDE.md](../CLAUDE.md). Tools: [../docs/tech.md](../docs/tech.md).

## Run

```bash
cd station
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m argos_station.main
```

Keys come from `station/.env` (falls back to the repo-root `.env`): `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and optionally `ARGOS_AIRPOD_NAME` (part of the AirPod's device name, default `AirPods`). Full list: [../docs/structure.md](../docs/structure.md) ("Env keys"). Never commit `.env`.

Connect the AirPod before starting: one connected later is not seen until a restart ([../docs/edge-cases.md](../docs/edge-cases.md), "Station").

### Try one module

Each module has a small test entry (run from `station/`, `--help` for options). None of them is wired into `main.py` until S2.3.

```bash
.venv/bin/python -m argos_station.sync --once     # pull people and files into data/ once
.venv/bin/python -m argos_station.voiceprints     # build or refresh voiceprints from data/
.venv/bin/python -m argos_station.listener        # print speech start/stop and clip events from the MacBook mic
.venv/bin/python -m argos_station.recognizer      # print who is speaking, "patient" or "unknown"; plays nothing
.venv/bin/python -m argos_station.player --sample # play a fictional sample reminder into the AirPod
.venv/bin/python -m argos_station.tracker --end-after 20 --same-within 60  # listener + recognizer + tracker + player, short timers
```

Unit tests (no mic, AirPod or Supabase needed):

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Local files (synced people, voice samples, reminder audio, voiceprints, models) live in `station/data/`, which is git-ignored.

## Where things go

- One job per module in `argos_station/`, as listed in [../docs/structure.md](../docs/structure.md): `sync`, `voiceprints`, `listener`, `recognizer`, `player`, `tracker`, `recorder`. `main.py` only wires them together. Folders, `.env` loading and the Supabase client come from `config.py`; never import from `main.py`.
- Dependencies go in `requirements.txt`, pinned (`==`).
- The station never calls an AI provider. Reminders are made ahead of time by the web app; the station only plays them.
- Tables in `supabase/migrations/` are the contract with the web app. Read and write them; don't change them from here.

## Rules

- **Silence over mistakes.** If unsure who is speaking, play nothing. On any error during a conversation, stay quiet and log it; never play a wrong or half-ready reminder.
- **Discreet.** Audio plays into the AirPod only, never through the MacBook speakers.
- **No real voices or recordings in git.** Voice samples, voiceprints, recordings and transcripts live in Supabase storage or in ignored local folders. Only fictional demo material goes in `demo/`.
