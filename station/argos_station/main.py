"""Starts the patient station. For now: connect to Supabase and prove it can read."""

import sys

from argos_station.config import connect, load_env


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
