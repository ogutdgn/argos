"""Shared setup for every station module: folders, .env keys and the Supabase client.

Lives here, not in main.py, so modules can use it without importing main.py,
which imports them to start them.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

STATION_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = STATION_DIR.parent

REQUIRED_KEYS = ("SUPABASE_URL", "SUPABASE_SECRET_KEY")


def load_env() -> None:
    # station/.env wins; the repo-root .env is the fallback.
    load_dotenv(STATION_DIR / ".env")
    load_dotenv(REPO_DIR / ".env")


def connect() -> Client:
    missing = [key for key in REQUIRED_KEYS if not os.environ.get(key)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}")
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
