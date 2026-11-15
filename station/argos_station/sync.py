"""Pulls people, voice samples and reminder audio from Supabase to the Mac.

Every 30 seconds (``SYNC_INTERVAL_SECONDS``) sync reads the ``people`` table
together with each person's newest ``reminders`` row, downloads any file the
Mac does not have yet, removes what is gone from Supabase, and rewrites a small
index. A person added in Supabase is on the Mac, with their files, by the next
pass, so well within a minute.

Local layout
------------

Everything lives in ``station/data/`` (ignored by git)::

    station/data/
    ├── index.json                               what was synced: read this
    ├── voice-samples/{person_id}/{uuid}.{ext}   same path as in the bucket
    └── reminder-audio/{person_id}/{reminder_id}.mp3

Only ``index.json`` and the two folders above belong to sync. Sync deletes any
file in those two folders that the index does not point at. Other modules keep
their own folders next to them (for example ``station/data/voiceprints/``);
sync never touches those.

index.json
----------

::

    {
      "synced_at": "2026-11-15T06:30:00+00:00",
      "people": [
        {
          "id": "<people.id>",
          "name": "Odysseus",
          "relationship": "son",              # null for the patient
          "is_patient": false,
          "voice_sample_file": "voice-samples/<person_id>/<uuid>.webm",  # or null
          "reminder": {                       # the newest reminder, or null
            "id": "<reminders.id>",
            "text": "This is Odysseus, your son. ...",
            "created_at": "...",
            "audio_file": "reminder-audio/<person_id>/<reminder_id>.mp3"
          }
        }
      ]
    }

File paths are relative to ``station/data/``. Other modules should not parse
the JSON themselves; call ``load_people()``, which returns ``SyncedPerson``
objects with absolute paths and drops any file that is not on disk.

Guarantees
----------

- **No half files.** Every file is downloaded under a temporary ``.part`` name
  and renamed when complete; ``index.json`` is replaced in one step the same
  way. A file the index points at is always whole.
- **New voice sample = new file.** The web gives every upload a new path, so
  a changed ``voice_sample_file`` means a new sample. S1.2: recompute the
  voiceprint when it changes.
- **Removed people disappear.** A person deleted in Supabase drops out of the
  index, and their files are deleted on the same pass. So do old voice samples
  and old reminders.
- **Failures keep what was there.** If one download fails, that person keeps
  what was synced before (their older sample or reminder is still theirs), and
  sync tries again next pass. If there was nothing before, the field is null.
  If Supabase cannot be reached, nothing local changes.
- **Unsure = nobody.** A missing or unreadable index reads as no people, so
  the station stays silent.

Only one sync should run at a time against the same folder.

Test entry: ``python -m argos_station.sync`` (runs until Ctrl-C) or
``python -m argos_station.sync --once``.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from supabase import Client

from argos_station.main import STATION_DIR, connect, load_env

DATA_DIR = STATION_DIR / "data"
INDEX_NAME = "index.json"
VOICE_BUCKET = "voice-samples"
REMINDER_BUCKET = "reminder-audio"
SYNCED_BUCKETS = (VOICE_BUCKET, REMINDER_BUCKET)
TEMP_SUFFIX = ".part"

# A pass every 30 s keeps "added in Supabase → on the Mac" under a minute,
# even with a slow download in the pass that picks the person up.
SYNC_INTERVAL_SECONDS = 30

log = logging.getLogger(__name__)


# Reading what was synced ---------------------------------------------------


@dataclass(frozen=True)
class SyncedReminder:
    id: str
    text: str
    created_at: str
    audio_file: Path  # absolute, complete mp3


@dataclass(frozen=True)
class SyncedPerson:
    id: str
    name: str
    relationship: str | None  # None for the patient
    is_patient: bool
    voice_sample_file: Path | None  # absolute; None if there is no sample yet
    reminder: SyncedReminder | None  # the current reminder; None if there is none yet


def load_people(data_dir: Path = DATA_DIR) -> list[SyncedPerson]:
    """Everyone synced so far. Empty if nothing was synced or the index is unreadable."""
    data_dir = Path(data_dir).resolve()
    people = []
    for entry in _read_index(data_dir).get("people", []):
        try:
            people.append(_person_from_entry(data_dir, entry))
        except (KeyError, TypeError, ValueError) as error:
            log.warning("skipping unreadable person in %s: %s", INDEX_NAME, error)
    return people


def _person_from_entry(data_dir: Path, entry: dict[str, Any]) -> SyncedPerson:
    reminder = None
    raw_reminder = entry.get("reminder")
    if raw_reminder:
        audio_file = _existing_file(data_dir, raw_reminder["audio_file"])
        if audio_file is not None:
            reminder = SyncedReminder(
                id=str(raw_reminder["id"]),
                text=str(raw_reminder["text"]),
                created_at=str(raw_reminder["created_at"]),
                audio_file=audio_file,
            )
    return SyncedPerson(
        id=str(entry["id"]),
        name=str(entry["name"]),
        relationship=entry.get("relationship"),
        is_patient=bool(entry["is_patient"]),
        voice_sample_file=_existing_file(data_dir, entry.get("voice_sample_file")),
        reminder=reminder,
    )


def _existing_file(data_dir: Path, relative: str | None) -> Path | None:
    if not relative:
        return None
    path = (data_dir / relative).resolve()
    if data_dir not in path.parents or not path.is_file():
        return None
    return path


def _read_index(data_dir: Path) -> dict[str, Any]:
    try:
        index = json.loads((data_dir / INDEX_NAME).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        log.warning("could not read %s: %s", INDEX_NAME, error)
        return {}
    if not isinstance(index, dict) or not isinstance(index.get("people"), list):
        log.warning("%s has an unexpected shape; ignoring it", INDEX_NAME)
        return {}
    return index


# Syncing -------------------------------------------------------------------


def fetch_people(client: Client) -> list[dict[str, Any]]:
    """People rows, each with its newest reminder embedded (a list of 0 or 1)."""
    response = (
        client.table("people")
        .select(
            "id, name, relationship, is_patient, voice_sample_path, "
            "reminders(id, text, audio_path, created_at)"
        )
        .order("created_at", desc=True, foreign_table="reminders")
        .limit(1, foreign_table="reminders")
        .execute()
    )
    return response.data


def sync_once(client: Client, data_dir: Path = DATA_DIR) -> dict[str, Any]:
    """One full pass. Returns the new index. Raises if Supabase cannot be read."""
    data_dir = Path(data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    _remove_temp_files(data_dir)

    rows = fetch_people(client)  # on failure, raise before touching anything
    before = {entry.get("id"): entry for entry in _read_index(data_dir).get("people", [])}
    people = [_sync_person(client, data_dir, row, before.get(row["id"]) or {}) for row in rows]

    index = {"synced_at": datetime.now(timezone.utc).isoformat(), "people": people}
    _write_atomic(data_dir / INDEX_NAME, json.dumps(index, indent=2, ensure_ascii=False).encode())
    _remove_unreferenced(data_dir, people)
    return index


def _sync_person(
    client: Client, data_dir: Path, row: dict[str, Any], before: dict[str, Any]
) -> dict[str, Any]:
    voice_sample_file = None
    if row.get("voice_sample_path"):
        voice_sample_file = _fetch_file(client, data_dir, VOICE_BUCKET, row["voice_sample_path"])
        if voice_sample_file is None and _existing_file(data_dir, before.get("voice_sample_file")):
            voice_sample_file = before["voice_sample_file"]  # keep the older sample for now

    reminder = None
    newest = (row.get("reminders") or [None])[0]
    if newest:
        audio_file = _fetch_file(client, data_dir, REMINDER_BUCKET, newest["audio_path"])
        if audio_file is not None:
            reminder = {
                "id": newest["id"],
                "text": newest["text"],
                "created_at": newest["created_at"],
                "audio_file": audio_file,
            }
        else:
            old = before.get("reminder")
            if old and _existing_file(data_dir, old.get("audio_file")):
                reminder = old  # keep the older reminder for now

    return {
        "id": row["id"],
        "name": row["name"],
        "relationship": row.get("relationship"),
        "is_patient": bool(row.get("is_patient")),
        "voice_sample_file": voice_sample_file,
        "reminder": reminder,
    }


def _fetch_file(client: Client, data_dir: Path, bucket: str, path: str) -> str | None:
    """Make sure bucket/path is on the Mac. Returns it relative to data_dir, or None."""
    root = data_dir / bucket
    target = (root / path).resolve()
    if root not in target.parents or target.name.endswith(TEMP_SUFFIX):
        log.warning("skipping unexpected path %r in %s", path, bucket)
        return None
    relative = target.relative_to(data_dir).as_posix()
    if target.is_file():
        return relative  # paths are never reused for new content, so this is current

    try:
        content = client.storage.from_(bucket).download(path)
        if not content:
            raise ValueError("empty file")
        _write_atomic(target, content)
    except Exception as error:  # noqa: BLE001 - any failure: keep the old copy, retry next pass
        log.warning("could not download %s/%s: %s", bucket, path, error)
        return None
    log.info("downloaded %s/%s", bucket, path)
    return relative


def _write_atomic(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=TEMP_SUFFIX)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, target)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp)
        raise


def _remove_temp_files(data_dir: Path) -> None:
    """Leftovers from a pass that was killed mid-download."""
    leftovers = list(data_dir.glob(f".{INDEX_NAME}.*{TEMP_SUFFIX}"))
    for bucket in SYNCED_BUCKETS:
        leftovers += (data_dir / bucket).rglob(f"*{TEMP_SUFFIX}")
    for leftover in leftovers:
        with contextlib.suppress(FileNotFoundError):
            leftover.unlink()


def _remove_unreferenced(data_dir: Path, people: list[dict[str, Any]]) -> None:
    keep = set()
    for person in people:
        if person["voice_sample_file"]:
            keep.add((data_dir / person["voice_sample_file"]).resolve())
        if person["reminder"]:
            keep.add((data_dir / person["reminder"]["audio_file"]).resolve())

    for bucket in SYNCED_BUCKETS:
        root = data_dir / bucket
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*"), reverse=True):  # files before their folders
            if path.is_file() and path.resolve() not in keep:
                path.unlink()
                log.info("removed %s", path.relative_to(data_dir).as_posix())
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()


def run_forever(
    client: Client,
    interval: float = SYNC_INTERVAL_SECONDS,
    data_dir: Path = DATA_DIR,
    stop: threading.Event | None = None,
) -> None:
    """Sync every `interval` seconds until `stop` is set. Errors are logged, never raised."""
    stop = stop or threading.Event()
    last_people = None
    while not stop.is_set():
        started = time.monotonic()
        try:
            index = sync_once(client, data_dir)
        except Exception:  # noqa: BLE001 - keep the local copy and try again next pass
            log.exception("sync failed; keeping the local copy")
        else:
            if index["people"] != last_people:
                log.info("synced:\n%s", describe(index["people"]))
                last_people = index["people"]
        stop.wait(max(0.0, interval - (time.monotonic() - started)))


def describe(people: list[dict[str, Any]]) -> str:
    """One line per person, for the test entry and logs."""
    if not people:
        return "  (nobody)"
    lines = []
    for person in people:
        who = "patient" if person["is_patient"] else (person["relationship"] or "?")
        voice = "yes" if person["voice_sample_file"] else "no"
        reminder = "yes" if person["reminder"] else "no"
        lines.append(f"  {person['name']} ({who}): voice sample {voice}, reminder {reminder}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync people and their files from Supabase.")
    parser.add_argument("--once", action="store_true", help="sync one time and exit")
    parser.add_argument(
        "--interval",
        type=float,
        default=SYNC_INTERVAL_SECONDS,
        help=f"seconds between passes (default {SYNC_INTERVAL_SECONDS})",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    load_env()
    client = connect()
    if args.once:
        index = sync_once(client)
        print(f"Synced to {DATA_DIR}:\n{describe(index['people'])}")
        return
    log.info("syncing every %g s into %s (Ctrl-C to stop)", args.interval, DATA_DIR)
    with contextlib.suppress(KeyboardInterrupt):
        run_forever(client, args.interval)


if __name__ == "__main__":
    main()
