"""Answers "whose voice is this?", or "unknown" when not sure.

The recognizer takes one speech clip from the listener (``SpeechClip``: the
first 3–5 s of someone speaking), turns it into a voiceprint with the same
model and the same ``voiceprints.embed()`` that made the stored voiceprints,
and compares it with every stored voiceprint (cosine similarity). The rule is
the one measured in S0.2 and recorded in ``docs/tech.md`` ("Voice recognition
threshold"):

- best score **at or above** ``THRESHOLD`` → that person;
- below it → unknown.

Each result is one of three kinds:

- ``VISITOR``: a registered visitor, with ``person_id``, ``name`` and
  ``score``. The only kind a caller may act on.
- ``PATIENT``: the best match is the patient's own voiceprint. The patient is
  speaking: **play nothing**. ``person_id`` and ``name`` stay empty, so the
  patient can never be taken for a visitor.
- ``UNKNOWN``: nobody scored high enough, there are no voiceprints, the clip
  was too short, near-silent or unreadable, or anything went wrong.
  **Play nothing.**

Silence over mistakes: ``recognize()`` never raises; any failure is logged
and comes back as ``UNKNOWN``.

For S2.1 (the tracker)
----------------------

::

    from argos_station.recognizer import Kind, Recognizer

    recognizer = Recognizer()                 # loads the model once; slow the first time
    result = recognizer.recognize(clip)       # clip: listener.SpeechClip
    if result.kind is Kind.VISITOR:
        ...                                   # result.person_id, result.name, result.score
    # Kind.PATIENT and Kind.UNKNOWN: say nothing

Each clip is judged on its own; the recognizer keeps no memory of earlier
clips. Who is already in the conversation, two visitors at once, and playing
reminders are the tracker's job.

``recognize()`` takes about a second on the MacBook CPU. The listener calls
``on_clip`` on its own thread and holds back its next events while a callback
runs, so the tracker should hand clips to its own worker thread. Calls are
safe from any thread; they run one at a time.

Voiceprints are reloaded when they change on disk: before each clip the
recognizer checks ``station/data/index.json`` and the files in
``station/data/voiceprints/`` (a few ``stat`` calls), and calls
``voiceprints.load_voiceprints()`` again only if something changed. The model
is loaded once and kept.

Logging: every decision is logged at INFO with the clip length, the time it
took and every person's score (person id, name, patient flag). Audio is never
logged or saved.

Test entry: ``python -m argos_station.recognizer`` listens on the MacBook mic
and prints one line per clip; ``--file a.wav b.wav`` judges audio files
instead. It plays nothing.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from argos_station import voiceprints
from argos_station.listener import MIN_CLIP_SECONDS, SAMPLE_RATE, SpeechClip
from argos_station.sync import DATA_DIR, INDEX_NAME
from argos_station.voiceprints import VOICEPRINTS_NAME, Voiceprint

# Cosine similarity at or above which the best match counts as that person.
# Measured in S0.2: docs/tech.md, "Voice recognition threshold". Only valid for
# embeddings made by voiceprints.embed() with voiceprints.MODEL_SOURCE.
THRESHOLD = 0.455

# A clip quieter than this is not judged (same speech-level check and number as
# voice samples in voiceprints.py). The listener already sends only speech;
# this catches a mic that went silent or a broken clip.
MIN_LEVEL_DBFS = voiceprints.MIN_LEVEL_DBFS

log = logging.getLogger(__name__)


class Kind(str, Enum):
    VISITOR = "visitor"  # a registered visitor: the only kind to act on
    PATIENT = "patient"  # the patient is speaking: say nothing
    UNKNOWN = "unknown"  # not sure, nobody known, or an error: say nothing


@dataclass(frozen=True)
class Score:
    person_id: str
    name: str
    is_patient: bool
    score: float  # cosine similarity, -1..1


@dataclass(frozen=True)
class Recognition:
    kind: Kind
    reason: str  # why, for the log: "match", "patient", "below threshold", "no voiceprints", ...
    person_id: str | None = None  # VISITOR only
    name: str | None = None  # VISITOR only
    score: float | None = None  # VISITOR only: their score
    scores: tuple[Score, ...] = field(default=())  # everyone, best first; empty if not scored
    clip_started_at: float | None = None  # SpeechClip.started_at, if a SpeechClip was given

    @property
    def best(self) -> Score | None:
        return self.scores[0] if self.scores else None

    def describe(self) -> str:
        """One line for people: "Odysseus (0.71)", "patient (0.68)", "unknown (best Odysseus 0.31)"."""
        best = self.best
        if self.kind is Kind.VISITOR:
            return f"{self.name} ({self.score:.2f})"
        if self.kind is Kind.PATIENT:
            assert best is not None
            return f"patient ({best.score:.2f})"
        if best is not None:
            return f"unknown (best {best.name} {best.score:.2f})"
        return f"unknown: {self.reason}"


class Recognizer:
    """Judges speech clips against the stored voiceprints. Load once, call often."""

    def __init__(self, data_dir: Path = DATA_DIR, model: Any = None, threshold: float = THRESHOLD):
        self.data_dir = Path(data_dir).resolve()
        self.threshold = threshold
        if threshold != THRESHOLD:
            log.warning("using threshold %.3f instead of the measured %.3f", threshold, THRESHOLD)
        self._model = model if model is not None else voiceprints.load_model(self.data_dir)
        self._lock = threading.Lock()
        self._voiceprints: list[Voiceprint] = []
        self._signature: tuple | None = None

    def recognize(self, clip: SpeechClip | np.ndarray, sample_rate: int = SAMPLE_RATE) -> Recognition:
        """Who is speaking in this clip. Never raises: any problem is UNKNOWN."""
        started = time.monotonic()
        clip_started_at = clip.started_at if isinstance(clip, SpeechClip) else None
        seconds = None
        try:
            if isinstance(clip, SpeechClip):
                audio, sample_rate = clip.audio, clip.sample_rate
            else:
                audio = clip
            audio = np.asarray(audio, dtype=np.float32)
            if audio.ndim == 2:
                audio = audio.mean(axis=1)
            seconds = audio.size / sample_rate if sample_rate > 0 else 0.0
            with self._lock:
                result = self._judge(audio, sample_rate, seconds)
        except Exception as error:  # noqa: BLE001 - silence over mistakes
            log.exception("recognition failed; treating the voice as unknown")
            result = Recognition(Kind.UNKNOWN, f"error: {type(error).__name__}")
        result = _with_clip_time(result, clip_started_at)
        _log_decision(result, seconds, time.monotonic() - started)
        return result

    @property
    def voiceprints(self) -> list[Voiceprint]:
        """The voiceprints currently in use (reloaded if they changed on disk)."""
        with self._lock:
            self._reload_if_changed()
            return list(self._voiceprints)

    # Inside the lock ------------------------------------------------------

    def _judge(self, audio: np.ndarray, sample_rate: int, seconds: float) -> Recognition:
        problem = _clip_problem(audio, sample_rate, seconds)
        if problem is not None:
            return Recognition(Kind.UNKNOWN, problem)

        self._reload_if_changed()
        if not self._voiceprints:
            return Recognition(Kind.UNKNOWN, "no voiceprints")

        clip_print = voiceprints.embed(self._model, audio, sample_rate)
        if clip_print.shape != (voiceprints.EMBEDDING_SIZE,) or not np.all(np.isfinite(clip_print)):
            return Recognition(Kind.UNKNOWN, "bad clip voiceprint")

        scores = tuple(
            sorted(
                (
                    Score(vp.person_id, vp.name, vp.is_patient, float(clip_print @ vp.embedding))
                    for vp in self._voiceprints
                ),
                key=lambda s: s.score,
                reverse=True,
            )
        )
        best = scores[0]
        if not math.isfinite(best.score) or best.score < self.threshold:
            return Recognition(Kind.UNKNOWN, "below threshold", scores=scores)
        if best.is_patient:
            return Recognition(Kind.PATIENT, "patient", scores=scores)
        return Recognition(
            Kind.VISITOR, "match", person_id=best.person_id, name=best.name, score=best.score, scores=scores
        )

    def _reload_if_changed(self) -> None:
        signature = _disk_signature(self.data_dir)
        if signature == self._signature:
            return
        try:
            loaded = voiceprints.load_voiceprints(self.data_dir)
        except Exception:  # noqa: BLE001 - know nobody rather than someone stale
            log.exception("could not load voiceprints; knowing nobody until they load")
            self._voiceprints, self._signature = [], None
            return
        self._voiceprints, self._signature = loaded, signature
        patients = [vp for vp in loaded if vp.is_patient]
        log.info(
            "loaded %d voiceprints: %s",
            len(loaded),
            ", ".join(f"{vp.person_id} {vp.name}{' (patient)' if vp.is_patient else ''}" for vp in loaded)
            or "none",
        )
        if loaded and not patients:
            log.warning("no voiceprint for the patient: their own voice cannot be recognized as theirs")


def _clip_problem(audio: np.ndarray, sample_rate: int, seconds: float) -> str | None:
    """Why this clip cannot be judged safely, or None if it can."""
    if audio.ndim != 1 or audio.size == 0 or sample_rate <= 0:
        return "bad clip"
    if not np.all(np.isfinite(audio)):
        return "bad clip"
    if seconds < MIN_CLIP_SECONDS - 1e-6:
        return f"clip too short ({seconds:.1f} s)"
    if voiceprints._speech_level_dbfs(audio, sample_rate) < MIN_LEVEL_DBFS:
        return "clip too quiet"
    return None


def _disk_signature(data_dir: Path) -> tuple:
    """What load_voiceprints() depends on, cheaply: the index and the voiceprint files.

    Files are replaced by rename (sync and voiceprints both do), so any change gives
    a new inode, mtime or size.
    """
    entries = []
    for path in [data_dir / INDEX_NAME, *_voiceprint_files(data_dir)]:
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        entries.append((path.name, stat.st_ino, stat.st_mtime_ns, stat.st_size))
    return tuple(entries)


def _voiceprint_files(data_dir: Path) -> list[Path]:
    try:
        return sorted(
            Path(entry.path)
            for entry in os.scandir(data_dir / VOICEPRINTS_NAME)
            if entry.name.endswith(".json") and not entry.name.startswith(".")
        )
    except FileNotFoundError:
        return []


def _with_clip_time(result: Recognition, clip_started_at: float | None) -> Recognition:
    if clip_started_at is None:
        return result
    return Recognition(
        result.kind,
        result.reason,
        result.person_id,
        result.name,
        result.score,
        result.scores,
        clip_started_at,
    )


def _log_decision(result: Recognition, seconds: float | None, took: float) -> None:
    scores = ", ".join(
        f"{s.person_id} {s.name}{' (patient)' if s.is_patient else ''} {s.score:.3f}" for s in result.scores
    )
    log.info(
        "%s: %s | clip %s, took %.2f s, threshold %.3f | scores: %s",
        result.kind.value,
        result.reason,
        f"{seconds:.2f} s" if seconds is not None else "?",
        took,
        THRESHOLD,
        scores or "none",
    )


# Test entry -------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Say who is speaking, one line per clip. Plays nothing."
    )
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help=f"default {DATA_DIR}")
    parser.add_argument("--file", nargs="+", type=Path, help="judge these audio files instead of the mic")
    parser.add_argument("--seconds", type=float, default=4.0, help="clip length from the mic, 3-5 (default 4)")
    parser.add_argument("--mic", help="input device name (default: the MacBook's built-in mic)")
    parser.add_argument("--quiet", action="store_true", help="only the result lines, no decision log")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    print("Loading the speaker model...")
    recognizer = Recognizer(args.data_dir)
    known = recognizer.voiceprints
    print(f"Voiceprints: {', '.join(vp.name + (' (patient)' if vp.is_patient else '') for vp in known) or 'none'}")
    if not known:
        print("  (none: run python -m argos_station.sync --once, then python -m argos_station.voiceprints)")

    if args.file:
        import soundfile as sf

        for path in args.file:
            try:
                audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)
            except Exception as error:  # noqa: BLE001 - report and go on
                print(f"{path.name}: cannot read ({error})")
                continue
            print(f"{path.name}: {recognizer.recognize(audio, sample_rate).describe()}")
        return

    from argos_station.listener import Listener, MicNotFoundError

    def clip_ready(clip: SpeechClip) -> None:
        print(recognizer.recognize(clip).describe(), flush=True)

    listener = Listener(on_clip=clip_ready, clip_seconds=args.seconds, mic_name=args.mic)
    try:
        listener.start()
    except MicNotFoundError:
        raise SystemExit(1) from None
    print("Speak (at least 3 s); one line per clip. Plays nothing. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        listener.stop()


if __name__ == "__main__":
    main()
