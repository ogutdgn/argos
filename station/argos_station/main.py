"""Starts the patient station. For now: connect to Supabase and prove it can read."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

STATION_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = STATION_DIR.parent

REQUIRED_KEYS = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")


def load_env() -> None:
    # station/.env wins; the repo-root .env is the fallback.
    load_dotenv(STATION_DIR / ".env")
    load_dotenv(REPO_DIR / ".env")


def connect() -> Client:
    missing = [key for key in REQUIRED_KEYS if not os.environ.get(key)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}")
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def main() -> None:
    load_env()
    client = connect()
    try:
        buckets = client.storage.list_buckets()
    except Exception as error:  # noqa: BLE001 - report any connection failure plainly
        sys.exit(f"Could not read from Supabase: {error}")
    names = ", ".join(bucket.name for bucket in buckets) or "none yet"
    print(f"Connected to Supabase. Storage buckets: {names}")


if __name__ == "__main__":
    main()
