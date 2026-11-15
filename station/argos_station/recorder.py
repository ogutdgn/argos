"""Records the conversation and uploads it.

The recorder takes every raw frame from the listener (``on_audio``) and the
tracker's four hooks. It only writes audio while the tracker has a
conversation open, and the tracker only opens one for a recognized visitor,
so a conversation with only unknown voices is never recorded or uploaded
(docs/edge-cases.md, "Unknown voice").

What is in a recording (decided 2026-11-15, S2.2; docs/edge-cases.md,
"What a recording holds"):

- **Pre-roll.** The last ``PRE_ROLL_SECONDS`` of mic audio are kept in memory
  only. When a conversation starts, they go first into the recording, so the
  greeting that led to the recognition (3-5 s of speech plus about a second
  of recognition) is not lost. Audio older than that is dropped and never
  written anywhere.
- **Away.** When the visitors count as away (5 min not heard), the recording
  pauses. Audio from then on is not kept. If one of them returns, the
  recording goes on with the pre-roll before the return, so the gap is cut
  out and the "I'm back" is in.
- **End.** The recording stops at the end. A conversation that ended because
  nobody came back stopped recording when it went away, so it ends about
  5 min after the visitors were last heard (the goodbye is in it).
- **Station stopped.** ``tracker.stop()`` ends the conversation with
  ``end_reason="station stopped"``; it is uploaded like any other. Stop the
  tracker before the recorder, so ``recorder.stop()`` can wait for the upload.
- **At most ``MAX_RECORDING_SECONDS``** (4 h). Past that nothing more is
  written; the first 4 h are uploaded.

Format: OGG Opus, 16 kHz mono, written as the audio comes in (libsndfile
through ``soundfile``, already a dependency). About 24 kbps even for loud
noise, so 4 h is about 44 MB, under the 50 MB ``recordings`` bucket limit.
The size is checked again before the upload.

When a conversation ends (docs/structure.md, "Station → web handoff"):

1. The file and a small job file (``{id}.json``: times, visitors, how far it
   got) are in ``data/recordings/``.
2. Upload to ``recordings/{conversation_id}.ogg``.
3. Insert the ``conversations`` row (``status='uploaded'``) and one
   ``conversation_people`` row per visitor. Only after the upload worked, so a
   row never points at a missing file.
4. ``POST {ARGOS_WEB_URL}/api/conversations/process``. 200 and 202 are done.
   5xx and network errors are retried (``ENDPOINT_TRIES`` tries, waits in
   ``ENDPOINT_BACKOFF_SECONDS``); 4xx is logged and never retried.

Each step is saved in the job file, so a step that failed is tried again from
there when the recorder next starts (or with ``--retry``), never twice. The
local audio is deleted once it is in storage and the rows are in; the job file
goes once the endpoint has accepted it, or rejected it with a 4xx (send it
again by hand with ``--notify``). Upload and inserts are idempotent (upsert,
ignore duplicates), and so is the endpoint, so a retry is always safe.

Silence over mistakes: nothing here ever plays audio, raises into the
listener or tracker, or stops the station. Errors are logged.

For S2.3 (main.py)
------------------

::

    from argos_station.recorder import Recorder

    recorder = Recorder()          # client from config.connect(), env read when needed
    tracker = Tracker(
        recognizer,
        on_start=recorder.on_start,
        on_away=recorder.on_away,
        on_return=recorder.on_return,
        on_end=recorder.on_end,
    )
    listener = Listener(on_clip=tracker.on_clip, on_audio=recorder.on_audio)
    recorder.start()               # upload thread; also retries what an earlier run left
    tracker.start()
    listener.start()
    ...
    listener.stop()
    tracker.stop()                 # ends an open conversation → on_end
    recorder.stop()                # waits up to STOP_WAIT_SECONDS for uploads

Needs ``SUPABASE_URL``, ``SUPABASE_SECRET_KEY``, ``ARGOS_WEB_URL`` and
``STATION_API_SECRET`` in ``.env``. Without them it still records; the job
waits in ``data/recordings/`` and is logged.

Test entry (listener + recognizer + tracker + player + recorder)::

    python -m argos_station.recorder --end-after 20 --same-within 60
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from argos_station.listener import FRAME_SAMPLES, SAMPLE_RATE
from argos_station.sync import DATA_DIR

if TYPE_CHECKING:
    from supabase import Client

    from argos_station.tracker import Conversation

log = logging.getLogger(__name__)

RECORDINGS_DIR_NAME = "recordings"  # data/recordings/: recordings waiting to be uploaded
BUCKET = "recordings"
EXTENSION = "ogg"
CONTENT_TYPE = "audio/ogg"
# libsndfile's Opus "compression level" sets the bitrate: 0.93 is about 24 kbps
# at 16 kHz mono, measured on full-level noise (the worst case; speech and
# silence come out smaller).
OPUS_COMPRESSION_LEVEL = 0.93

PRE_ROLL_SECONDS = 10.0  # Kept before the start and before a return: the greeting.
MAX_RECORDING_SECONDS = 4 * 60 * 60  # 4 h ≈ 44 MB at 24 kbps.
BUCKET_LIMIT_BYTES = 50 * 1024 * 1024  # The recordings bucket's file_size_limit.

ENDPOINT_PATH = "/api/conversations/process"
ENDPOINT_TRIES = 5  # For 5xx and network errors. 4xx: one try.
ENDPOINT_BACKOFF_SECONDS = (2.0, 4.0, 8.0, 16.0)  # Wait before tries 2..5 (30 s in all).
ENDPOINT_TIMEOUT_SECONDS = 15.0
STORAGE_TRIES = 3  # Upload and inserts, any error.
STORAGE_BACKOFF_SECONDS = (2.0, 4.0)
UPLOAD_TIMEOUT_SECONDS = 120  # supabase-py's default storage timeout is 20 s.
STOP_WAIT_SECONDS = 120.0  # recorder.stop() waits this long for uploads in flight.

# How far a job got (saved in its job file).
STAGE_RECORDED = "recorded"  # local file complete; nothing uploaded
STAGE_UPLOADED = "uploaded"  # file in storage; no rows yet
STAGE_SAVED = "saved"  # rows inserted; local audio deleted; endpoint not called yet
STAGE_TOO_LARGE = "too large"  # over the bucket limit: kept, never uploaded

# What the endpoint call came to.
NOTIFIED = "notified"  # 200 or 202
REJECTED = "rejected"  # 4xx or another status: logged, not retried
GAVE_UP = "gave up"  # 5xx or network errors on every try, or no URL/secret: kept for a later retry


def recordings_dir(data_dir: Path = DATA_DIR) -> Path:
    return data_dir / RECORDINGS_DIR_NAME


def _iso(at: float) -> str:
    return datetime.fromtimestamp(at, timezone.utc).isoformat()


@dataclass(frozen=True)
class Job:
    """One finished conversation on its way to Supabase (``{id}.json``)."""

    conversation_id: str
    started_at: float
    ended_at: float
    end_reason: str | None
    person_ids: tuple[str, ...]
    seconds: float  # length of the recording
    stage: str = STAGE_RECORDED

    @property
    def recording_path(self) -> str:
        """The path in the recordings bucket (and the local file name)."""
        return f"{self.conversation_id}.{EXTENSION}"

    def to_json(self) -> str:
        data = asdict(self)
        data["person_ids"] = list(self.person_ids)
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, text: str) -> Job:
        data = json.loads(text)
        data["person_ids"] = tuple(data["person_ids"])
        return cls(**data)


@dataclass
class _Recording:
    conversation_id: str
    path: Path
    file: Any  # soundfile.SoundFile
    max_samples: int
    samples: int = 0
    paused: bool = False
    full: bool = False
    failed: bool = False
    last_index: int = -1  # last frame number written (so a return never writes a frame twice)
    person_ids: tuple[str, ...] = field(default_factory=tuple)


def _default_client() -> Client:
    from argos_station.config import REQUIRED_KEYS, connect

    missing = [key for key in REQUIRED_KEYS if not os.environ.get(key)]
    if missing:
        raise RuntimeError(f"missing in .env: {', '.join(missing)}")
    client = connect()
    # Set before client.storage is first used: a long recording needs more than 20 s.
    client.options.storage_client_timeout = UPLOAD_TIMEOUT_SECONDS
    return client


class Recorder:
    """Records the open conversation and hands it to Supabase and the web app when it ends."""

    def __init__(
        self,
        *,
        data_dir: Path = DATA_DIR,
        client: Client | Callable[[], Client] | None = None,
        web_url: str | None = None,
        secret: str | None = None,
        pre_roll_seconds: float = PRE_ROLL_SECONDS,
        max_seconds: float = MAX_RECORDING_SECONDS,
        size_limit: int = BUCKET_LIMIT_BYTES,
        endpoint_tries: int = ENDPOINT_TRIES,
        endpoint_backoff: tuple[float, ...] = ENDPOINT_BACKOFF_SECONDS,
        storage_tries: int = STORAGE_TRIES,
        storage_backoff: tuple[float, ...] = STORAGE_BACKOFF_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        keep_local: bool = False,
    ) -> None:
        self.dir = recordings_dir(data_dir)
        # A client, or something that makes one (called once, on first use).
        self._client_source = client if client is not None else _default_client
        self._client: Client | None = None
        self._web_url = web_url  # None: $ARGOS_WEB_URL, read when needed
        self._secret = secret  # None: $STATION_API_SECRET, read when needed
        self.max_samples = round(max_seconds * SAMPLE_RATE)
        self.size_limit = size_limit
        self.endpoint_tries = max(1, endpoint_tries)
        self.endpoint_backoff = endpoint_backoff
        self.storage_tries = max(1, storage_tries)
        self.storage_backoff = storage_backoff
        self.sleep = sleep
        self.keep_local = keep_local  # test entry only: keep the audio after upload

        self._lock = threading.Lock()  # guards _recording and the pre-roll
        self._pre_roll: deque[tuple[int, np.ndarray]] = deque(
            maxlen=max(1, math.ceil(pre_roll_seconds * SAMPLE_RATE / FRAME_SAMPLES))
        )
        self._frame_index = 0
        self._recording: _Recording | None = None
        self._jobs: queue.Queue[str | None] = queue.Queue()  # conversation ids
        self._thread: threading.Thread | None = None

    # Listener ------------------------------------------------------------------

    def on_audio(self, frame: np.ndarray) -> None:
        """Listener callback: every raw mic frame. Kept for the pre-roll; written while recording."""
        with self._lock:
            self._frame_index += 1
            item = (self._frame_index, frame)
            self._pre_roll.append(item)
            recording = self._recording
            if recording is not None and not recording.paused:
                self._write(recording, [item])

    # Tracker hooks ---------------------------------------------------------------

    def on_start(self, conversation: Conversation) -> None:
        """A conversation started: open its file and write the pre-roll."""
        try:
            with self._lock:
                if self._recording is not None:
                    log.error(
                        "conversation %s started while %s was still recording; that one is kept locally, "
                        "not uploaded",
                        conversation.id[:8],
                        self._recording.conversation_id[:8],
                    )
                    self._close(self._recording)
                    self._recording = None
                self._recording = self._open(conversation.id)
                if self._recording is not None:
                    self._write(self._recording, list(self._pre_roll))
                    log.info("recording conversation %s", conversation.id[:8])
        except Exception:  # noqa: BLE001 - never raise into the tracker
            log.exception("could not start recording conversation %s", conversation.id[:8])

    def on_away(self, conversation: Conversation) -> None:
        """The visitors are away: pause. Nothing more is written unless one of them returns."""
        with self._lock:
            recording = self._current(conversation)
            if recording is not None:
                recording.paused = True
                log.info("conversation %s away: recording paused", conversation.id[:8])

    def on_return(self, conversation: Conversation) -> None:
        """One of them is back: go on, starting with the pre-roll before the return."""
        with self._lock:
            recording = self._current(conversation)
            if recording is not None:
                recording.paused = False
                self._write(recording, [item for item in self._pre_roll if item[0] > recording.last_index])
                log.info("conversation %s back: recording again", conversation.id[:8])

    def on_end(self, conversation: Conversation) -> None:
        """Over: close the file, save the job and queue it for upload. Never raises."""
        try:
            with self._lock:
                recording = self._current(conversation)
                if recording is None:
                    log.warning("conversation %s ended with no recording; nothing to upload", conversation.id[:8])
                    return
                self._recording = None
                closed = self._close(recording)
            if recording.failed or not closed:
                log.error(
                    "recording of conversation %s failed; kept in %s, not uploaded", conversation.id[:8], self.dir
                )
                return
            job = Job(
                conversation_id=conversation.id,
                started_at=conversation.started_at,
                ended_at=conversation.ended_at if conversation.ended_at is not None else conversation.last_heard_at,
                end_reason=conversation.end_reason,
                person_ids=conversation.person_ids,
                seconds=round(recording.samples / SAMPLE_RATE, 2),
            )
            self._save(job)
            log.info(
                "conversation %s recorded (%.0f s, %s); queued for upload",
                conversation.id[:8],
                job.seconds,
                conversation.end_reason,
            )
            self._jobs.put(job.conversation_id)
        except Exception:  # noqa: BLE001
            log.exception("could not finish recording conversation %s", conversation.id[:8])

    # Thread --------------------------------------------------------------------------

    def start(self) -> None:
        """Start the upload thread and queue what an earlier run left in data/recordings/."""
        if self._thread is not None:
            return
        for conversation_id in self.pending():
            self._jobs.put(conversation_id)
        self._thread = threading.Thread(target=self._upload_loop, name="recorder-upload", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = STOP_WAIT_SECONDS) -> None:
        """Wait up to ``timeout`` for queued uploads, then stop. What is left stays for next time."""
        with self._lock:
            if self._recording is not None:
                log.warning(
                    "recorder stopped while conversation %s was still recording (stop the tracker first); "
                    "kept locally, not uploaded",
                    self._recording.conversation_id[:8],
                )
                self._close(self._recording)
                self._recording = None
        if self._thread is None:
            return
        self._jobs.put(None)
        self._thread.join(timeout)
        if self._thread.is_alive():
            log.warning("uploads still running after %.0f s; what is left is retried on the next start", timeout)
        self._thread = None

    def __enter__(self) -> Recorder:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def _upload_loop(self) -> None:
        while True:
            conversation_id = self._jobs.get()
            if conversation_id is None:
                return
            self.process(conversation_id)

    # Handing on ----------------------------------------------------------------------

    def pending(self) -> list[str]:
        """Conversation ids with a job file in data/recordings/, oldest first. Logs orphan recordings."""
        if not self.dir.exists():
            return []
        ids = []
        for path in sorted(self.dir.glob("*.json"), key=lambda p: p.stat().st_mtime):
            job = self._load(path.stem)
            if job is not None and job.stage != STAGE_TOO_LARGE:
                ids.append(job.conversation_id)
        for audio in self.dir.glob(f"*.{EXTENSION}"):
            if not audio.stem.endswith(".kept") and not (self.dir / f"{audio.stem}.json").exists():
                log.warning("%s has no job file (the recording never finished); kept, not uploaded", audio.name)
        return ids

    def process(self, conversation_id: str) -> str | None:
        """Take one job as far as it goes: upload, rows, endpoint. Returns the endpoint outcome. Never raises."""
        try:
            job = self._load(conversation_id)
            if job is None:
                return None
            if job.stage == STAGE_RECORDED:
                job = self._upload(job)
            if job is not None and job.stage == STAGE_UPLOADED:
                job = self._insert(job)
            if job is not None and job.stage == STAGE_SAVED:
                outcome = self.notify(job.conversation_id)
                if outcome != GAVE_UP:
                    self._job_path(job.conversation_id).unlink(missing_ok=True)
                return outcome
        except Exception:  # noqa: BLE001 - silence over mistakes
            log.exception("handing on conversation %s failed; kept in %s", conversation_id[:8], self.dir)
        return None

    def _upload(self, job: Job) -> Job | None:
        audio = self.dir / job.recording_path
        if not audio.exists():
            log.error("%s is missing; conversation %s cannot be uploaded", audio, job.conversation_id[:8])
            return None
        size = audio.stat().st_size
        if size > self.size_limit:
            log.error(
                "%s is %.1f MB, over the %.0f MB bucket limit; kept, not uploaded",
                audio.name,
                size / 1e6,
                self.size_limit / 1e6,
            )
            self._save(replace(job, stage=STAGE_TOO_LARGE))
            return None

        def upload() -> None:
            self.client().storage.from_(BUCKET).upload(
                job.recording_path, audio, {"content-type": CONTENT_TYPE, "upsert": "true"}
            )

        if not self._retry(f"upload of {audio.name}", upload):
            return None
        log.info("uploaded %s/%s (%.2f MB)", BUCKET, job.recording_path, size / 1e6)
        return self._save(replace(job, stage=STAGE_UPLOADED))

    def _insert(self, job: Job) -> Job | None:
        conversation_row = {
            "id": job.conversation_id,
            "started_at": _iso(job.started_at),
            "ended_at": _iso(job.ended_at),
            "recording_path": job.recording_path,
            "status": "uploaded",
        }
        people_rows = [{"conversation_id": job.conversation_id, "person_id": pid} for pid in job.person_ids]

        def insert() -> None:
            client = self.client()
            # ignore_duplicates: a retry never resets a status the web app has already moved on.
            client.table("conversations").upsert(conversation_row, ignore_duplicates=True).execute()
            if people_rows:
                client.table("conversation_people").upsert(people_rows, ignore_duplicates=True).execute()

        if not self._retry(f"rows for conversation {job.conversation_id[:8]}", insert):
            return None
        log.info("conversation %s saved with %d visitor(s)", job.conversation_id[:8], len(people_rows))
        job = self._save(replace(job, stage=STAGE_SAVED))
        audio = self.dir / job.recording_path
        if self.keep_local:
            audio.replace(audio.with_suffix(f".kept.{EXTENSION}"))  # test entry: to listen to it
        else:
            audio.unlink(missing_ok=True)
        return job

    def notify(self, conversation_id: str) -> str:
        """POST the processing endpoint. 200/202 → NOTIFIED; 4xx → REJECTED; 5xx/network → retried, then GAVE_UP."""
        web_url = self._web_url if self._web_url is not None else os.environ.get("ARGOS_WEB_URL", "")
        secret = self._secret if self._secret is not None else os.environ.get("STATION_API_SECRET", "")
        if not web_url or not secret:
            log.error(
                "ARGOS_WEB_URL or STATION_API_SECRET missing in .env; conversation %s not sent for processing "
                "(retried on the next start)",
                conversation_id[:8],
            )
            return GAVE_UP
        url = web_url.rstrip("/") + ENDPOINT_PATH
        body = json.dumps({"conversation_id": conversation_id}).encode()
        for attempt in range(1, self.endpoint_tries + 1):
            request = urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
            )
            status: int | None = None
            problem = ""
            try:
                with urllib.request.urlopen(request, timeout=ENDPOINT_TIMEOUT_SECONDS) as response:
                    status = response.status
            except urllib.error.HTTPError as error:
                status = error.code
                error.close()
            except (urllib.error.URLError, OSError) as error:  # network, DNS, refused, timeout
                problem = f"network error ({getattr(error, 'reason', error)})"
            if status in (200, 202):
                log.info("conversation %s sent for processing (%d)", conversation_id[:8], status)
                return NOTIFIED
            if status is not None and not 500 <= status < 600:
                log.error(
                    "processing endpoint answered %d for conversation %s; not retried (send it again with "
                    "`python -m argos_station.recorder --notify %s`)",
                    status,
                    conversation_id[:8],
                    conversation_id,
                )
                return REJECTED
            if status is not None:
                problem = f"status {status}"
            if attempt < self.endpoint_tries:
                wait = self.endpoint_backoff[min(attempt - 1, len(self.endpoint_backoff) - 1)]
                log.warning(
                    "processing endpoint: %s for conversation %s (try %d of %d); again in %.0f s",
                    problem,
                    conversation_id[:8],
                    attempt,
                    self.endpoint_tries,
                    wait,
                )
                self.sleep(wait)
            else:
                log.error(
                    "processing endpoint: %s for conversation %s on all %d tries; giving up (retried on the "
                    "next start)",
                    problem,
                    conversation_id[:8],
                    self.endpoint_tries,
                )
        return GAVE_UP

    # Helpers --------------------------------------------------------------------------

    def client(self) -> Client:
        if self._client is None:
            source = self._client_source
            self._client = source() if callable(source) else source
        return self._client

    def _retry(self, what: str, action: Callable[[], None]) -> bool:
        for attempt in range(1, self.storage_tries + 1):
            try:
                action()
                return True
            except Exception as error:  # noqa: BLE001 - logged; the job stays for a later retry
                if attempt < self.storage_tries:
                    wait = self.storage_backoff[min(attempt - 1, len(self.storage_backoff) - 1)]
                    log.warning("%s failed (try %d of %d): %s; again in %.0f s", what, attempt,
                                self.storage_tries, error, wait)
                    self.sleep(wait)
                else:
                    log.error("%s failed on all %d tries: %s; kept in %s for the next start", what,
                              self.storage_tries, error, self.dir)
        return False

    def _current(self, conversation: Conversation) -> _Recording | None:
        recording = self._recording
        if recording is None or recording.conversation_id != conversation.id:
            return None
        return recording

    def _open(self, conversation_id: str) -> _Recording | None:
        import soundfile as sf

        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{conversation_id}.{EXTENSION}"
        try:
            file = sf.SoundFile(
                path,
                "w",
                samplerate=SAMPLE_RATE,
                channels=1,
                format="OGG",
                subtype="OPUS",
                compression_level=OPUS_COMPRESSION_LEVEL,
            )
        except Exception:  # noqa: BLE001
            log.exception("could not open %s; conversation %s is not recorded", path, conversation_id[:8])
            return None
        return _Recording(conversation_id, path, file, self.max_samples)

    def _write(self, recording: _Recording, items: list[tuple[int, np.ndarray]]) -> None:
        if recording.failed or recording.full:
            return
        try:
            for index, frame in items:
                room = recording.max_samples - recording.samples
                if room <= 0:
                    recording.full = True
                    log.warning(
                        "conversation %s reached %.0f h of recording; nothing more is written",
                        recording.conversation_id[:8],
                        recording.max_samples / SAMPLE_RATE / 3600,
                    )
                    return
                chunk = np.asarray(frame, dtype=np.float32).reshape(-1)[:room]
                recording.file.write(chunk)
                recording.samples += len(chunk)
                recording.last_index = index
        except Exception:  # noqa: BLE001 - never raise into the listener
            recording.failed = True
            log.exception("writing conversation %s failed; it will not be uploaded", recording.conversation_id[:8])

    @staticmethod
    def _close(recording: _Recording) -> bool:
        try:
            recording.file.close()
            return True
        except Exception:  # noqa: BLE001
            log.exception("closing %s failed", recording.path.name)
            return False

    def _job_path(self, conversation_id: str) -> Path:
        return self.dir / f"{conversation_id}.json"

    def _save(self, job: Job) -> Job:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._job_path(job.conversation_id)
        temp = path.with_suffix(".json.part")
        temp.write_text(job.to_json())
        temp.replace(path)  # never a half-written job file
        return job

    def _load(self, conversation_id: str) -> Job | None:
        path = self._job_path(conversation_id)
        try:
            return Job.from_json(path.read_text())
        except FileNotFoundError:
            log.warning("no job file for conversation %s", conversation_id[:8])
        except Exception:  # noqa: BLE001
            log.exception("could not read %s; left as it is", path.name)
        return None


# Test entry -----------------------------------------------------------------------


def main() -> None:
    from argos_station.tracker import END_AFTER_SECONDS, SAME_CONVERSATION_SECONDS, Timing

    parser = argparse.ArgumentParser(
        description="Run listener + recognizer + tracker + player + recorder: each finished conversation is "
        "uploaded to Supabase and sent to the processing endpoint."
    )
    parser.add_argument("--end-after", type=float, default=END_AFTER_SECONDS,
                        help=f"seconds without a visitor's voice before they count as away (default {END_AFTER_SECONDS})")
    parser.add_argument("--same-within", type=float, default=SAME_CONVERSATION_SECONDS,
                        help="seconds since last heard within which a return is the same conversation "
                             f"(default {SAME_CONVERSATION_SECONDS})")
    parser.add_argument("--mic", help="input device name (default: the MacBook's built-in mic)")
    parser.add_argument("--device", help="part of the AirPod's output name (default: $ARGOS_AIRPOD_NAME or 'AirPods')")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help=f"default {DATA_DIR}")
    parser.add_argument("--dry-run", action="store_true", help="print which reminder would play instead of playing it")
    parser.add_argument("--keep-local", action="store_true",
                        help="keep the local recording after upload, as data/recordings/{id}.kept.ogg, to listen to it")
    parser.add_argument("--retry", action="store_true",
                        help="only hand on what earlier runs left in data/recordings/, then exit (no mic)")
    parser.add_argument("--notify", metavar="CONVERSATION_ID",
                        help="only call the processing endpoint for this conversation, then exit (no mic)")
    args = parser.parse_args()
    try:
        timing = Timing(args.end_after, args.same_within)
    except ValueError as error:
        parser.error(str(error))

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("argos_station.recognizer").setLevel(logging.WARNING)

    from argos_station.config import load_env

    load_env()
    for key in ("ARGOS_WEB_URL", "STATION_API_SECRET"):
        if not os.environ.get(key):
            print(f"Warning: {key} is not set in .env; conversations will be uploaded but not sent for processing.")

    recorder = Recorder(data_dir=args.data_dir, keep_local=args.keep_local)
    if args.notify:
        outcome = recorder.notify(args.notify)
        print(f"Processing endpoint: {outcome}")
        raise SystemExit(0 if outcome == NOTIFIED else 1)
    if args.retry:
        ids = recorder.pending()
        print(f"{len(ids)} conversation(s) waiting in {recorder.dir}")
        for conversation_id in ids:
            print(f"{conversation_id}: {recorder.process(conversation_id) or 'not finished (see the log)'}")
        return

    from argos_station.listener import Listener, MicNotFoundError
    from argos_station.recognizer import Recognizer
    from argos_station.tracker import Tracker

    if args.dry_run:
        def play(path: Path) -> bool:
            print(f"(dry run) would play {path.name}")
            return True
    else:
        from argos_station import player

        def play(path: Path) -> bool:
            return player.play(path, args.device)

    def show(label: str, hook: Callable[[Conversation], None]) -> Callable[[Conversation], None]:
        def both(conversation: Conversation) -> None:
            names = ", ".join(v.name for v in conversation.visitors) or "nobody yet"
            reason = f" ({conversation.end_reason})" if conversation.end_reason else ""
            print(f">>> {label}{reason}: conversation {conversation.id} with {names}", flush=True)
            hook(conversation)
        return both

    print("Loading the speaker model...")
    recognizer = Recognizer(args.data_dir)
    tracker = Tracker(
        recognizer,
        timing=timing,
        on_start=show("STARTED", recorder.on_start),
        on_away=show("AWAY", recorder.on_away),
        on_return=show("RETURNED", recorder.on_return),
        on_end=show("ENDED", recorder.on_end),
        play=play,
        data_dir=args.data_dir,
    )
    listener = Listener(on_clip=tracker.on_clip, on_audio=recorder.on_audio, mic_name=args.mic)
    recorder.start()
    tracker.start()
    try:
        listener.start()
    except MicNotFoundError:
        tracker.stop()
        recorder.stop()
        raise SystemExit(1) from None
    print(
        f"Away after {timing.end_after:.0f} s without a visitor, over {timing.same_conversation_within:.0f} s "
        "after last heard. Speak; Ctrl+C to stop (an open conversation is uploaded first)."
    )
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        listener.stop()
        tracker.stop()
        recorder.stop()


if __name__ == "__main__":
    main()
