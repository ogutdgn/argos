"""Turns each synced voice sample into a voiceprint.

A voiceprint is 192 numbers that describe how a person sounds. It comes from
SpeechBrain's ECAPA speaker model (``speechbrain/spkrec-ecapa-voxceleb``),
exactly as in the S0.2 test (``station/scripts/voice_test.py``): 16 kHz mono
audio in, embedding scaled to length 1. Two voiceprints are compared with
cosine similarity (a dot product, since both have length 1). The threshold
measured in S0.2 is in ``docs/tech.md`` ("Voice recognition threshold"); it is
only valid for embeddings made by ``embed()`` below, so S1.4 must embed its
clips with the same function.

For S1.4 (the recognizer)
-------------------------

::

    from argos_station import voiceprints

    model = voiceprints.load_model()              # once; slow the first time
    prints = voiceprints.load_voiceprints()       # list[Voiceprint]
    clip_print = voiceprints.embed(model, clip.audio)   # 16 kHz mono float32
    for vp in prints:
        score = float(clip_print @ vp.embedding)  # cosine similarity
        ...                                       # matching is S1.4's job

Each ``Voiceprint`` has ``person_id``, ``name``, ``is_patient`` and
``embedding`` (numpy float32, shape (192,), length 1). **A match on the
patient's voiceprint means the patient is speaking: say nothing.**

``load_voiceprints()`` only returns voiceprints that still fit what sync last
wrote: the person is in ``index.json`` and their voice sample is the one the
voiceprint was made from. Name and patient flag come from the index, so they
are always current. Anything missing or unreadable is left out; an empty list
means "know nobody", so the station stays silent. Call it again after each
``refresh()`` to pick up changes.

Building them
-------------

``refresh()`` reads people from sync (``sync.load_people()``, never Supabase)
and brings ``station/data/voiceprints/`` up to date:

- one voiceprint per person with a voice sample, the patient included;
- a person without a voice sample gets none (logged);
- a sample that cannot be read, is shorter than ``MIN_SAMPLE_SECONDS`` or is
  near-silent gives no voiceprint (logged), never a bad one;
- a changed ``voice_sample_file`` (each upload has a new path) means the
  voiceprint is made again; an unchanged one is reused without loading the
  model;
- voiceprints of people no longer in the index are deleted.

Local layout (ignored by git, sync never touches it)::

    station/data/voiceprints/{person_id}.json
    station/data/models/spkrec-ecapa-voxceleb/    the model, downloaded once

Each file holds ``person_id``, ``name``, ``is_patient``, ``voice_sample_file``
(relative to ``station/data/``, as in ``index.json``), ``model``,
``created_at`` and ``embedding``. Files are written under a temporary name and
renamed when complete, so a reader never sees half a file. Only one
``refresh()`` should run at a time against the same folder.

Voice samples from the web are WAV, 16 kHz mono 16-bit (``docs/tech.md``,
"Voice samples"). ``soundfile`` reads them, and also FLAC, OGG and MP3, with no
system tools. Formats it cannot read (for example webm) are skipped.

Test entry: ``python -m argos_station.voiceprints`` builds or refreshes the
voiceprints and prints one line per person.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from argos_station.sync import DATA_DIR, INDEX_NAME, SyncedPerson, load_people

VOICEPRINTS_NAME = "voiceprints"
MODELS_NAME = "models"
MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"  # same as S0.2: the threshold depends on it
SAMPLE_RATE = 16000
EMBEDDING_SIZE = 192
TEMP_SUFFIX = ".part"

# The web asks for 20–30 s with at least 10 s of speech. These are only a
# safety net for files that got past that: anything below gives no voiceprint.
MIN_SAMPLE_SECONDS = 10.0
MIN_LEVEL_DBFS = -50.0  # speech level (95th percentile of 30 ms frames); the web uses −40
FRAME_SECONDS = 0.03

log = logging.getLogger(__name__)


# Reading voiceprints (for S1.4) ---------------------------------------------


@dataclass(frozen=True)
class Voiceprint:
    person_id: str
    name: str
    is_patient: bool  # True: the patient is speaking, say nothing
    embedding: np.ndarray  # float32, shape (EMBEDDING_SIZE,), length 1


def load_voiceprints(data_dir: Path = DATA_DIR) -> list[Voiceprint]:
    """Voiceprints of everyone synced whose voiceprint fits their current sample."""
    data_dir = Path(data_dir).resolve()
    voiceprints = []
    for person in load_people(data_dir):
        if person.voice_sample_file is None:
            continue
        record = _read_record(_voiceprint_path(data_dir, person.id))
        if record is None or record.get("voice_sample_file") != _relative(data_dir, person):
            continue
        embedding = _valid_embedding(record.get("embedding"))
        if embedding is None:
            log.warning("ignoring voiceprint of %s: bad embedding", person.name)
            continue
        voiceprints.append(
            Voiceprint(
                person_id=person.id,
                name=person.name,
                is_patient=person.is_patient,
                embedding=embedding,
            )
        )
    return voiceprints


# Embedding (shared with S1.4) -----------------------------------------------


def load_model(data_dir: Path = DATA_DIR) -> Any:
    """The SpeechBrain speaker model. Downloads it once into station/data/models/."""
    from speechbrain.inference.speaker import EncoderClassifier  # slow import; only when needed

    return EncoderClassifier.from_hparams(
        source=MODEL_SOURCE,
        savedir=str(Path(data_dir) / MODELS_NAME / MODEL_SOURCE.split("/")[-1]),
        run_opts={"device": "cpu"},
    )


def embed(model: Any, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Audio (mono 1-D, or (frames, channels)) → voiceprint of length 1. Same method as S0.2."""
    import torch
    import torchaudio

    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    wav = torch.from_numpy(np.ascontiguousarray(audio))
    if sample_rate != SAMPLE_RATE:
        wav = torchaudio.functional.resample(wav, sample_rate, SAMPLE_RATE)
    with torch.no_grad():
        emb = model.encode_batch(wav.unsqueeze(0)).squeeze()
    return (emb / emb.norm()).numpy().astype(np.float32)


# Building voiceprints -------------------------------------------------------


@dataclass(frozen=True)
class RefreshResult:
    person_id: str
    name: str
    is_patient: bool
    ok: bool  # True: this person has a voiceprint now
    note: str  # "made", "unchanged", or why it was skipped


class _LazyModel:
    """Loads the model the first time it is needed, and only tries once."""

    def __init__(self, data_dir: Path, model: Any = None):
        self._data_dir = data_dir
        self._model = model
        self._error: Exception | None = None

    def get(self) -> Any:
        if self._model is None and self._error is None:
            try:
                self._model = load_model(self._data_dir)
            except Exception as error:  # noqa: BLE001 - report it per person, make nothing
                log.exception("could not load the speaker model")
                self._error = error
        if self._error is not None:
            raise RuntimeError(f"speaker model unavailable: {self._error}")
        return self._model


def refresh(data_dir: Path = DATA_DIR, model: Any = None) -> list[RefreshResult]:
    """Bring station/data/voiceprints/ in line with what sync wrote. Never raises per person."""
    data_dir = Path(data_dir).resolve()
    folder = data_dir / VOICEPRINTS_NAME
    folder.mkdir(parents=True, exist_ok=True)
    for leftover in folder.glob(f"*{TEMP_SUFFIX}"):
        with contextlib.suppress(FileNotFoundError):
            leftover.unlink()

    people = load_people(data_dir)
    lazy_model = _LazyModel(data_dir, model)
    results = [_refresh_person(data_dir, person, lazy_model) for person in people]

    if not (data_dir / INDEX_NAME).is_file():
        return results  # nothing synced yet: keep what is there until sync has run
    keep = {_voiceprint_path(data_dir, person.id).name for person in people}
    for path in folder.glob("*.json"):
        if path.name not in keep:
            path.unlink()
            log.info("removed voiceprint %s (no longer synced)", path.name)
    return results


def _refresh_person(data_dir: Path, person: SyncedPerson, lazy_model: _LazyModel) -> RefreshResult:
    path = _voiceprint_path(data_dir, person.id)

    def result(ok: bool, note: str) -> RefreshResult:
        return RefreshResult(person.id, person.name, person.is_patient, ok, note)

    def skip(note: str) -> RefreshResult:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()  # an old voiceprint no longer fits: better none than a wrong one
        level = logging.WARNING if person.is_patient else logging.INFO
        log.log(level, "no voiceprint for %s%s: %s",
                person.name, " (patient)" if person.is_patient else "", note)
        return result(False, note)

    if person.voice_sample_file is None:
        return skip("no voice sample")
    relative = _relative(data_dir, person)

    record = _read_record(path)
    if (
        record is not None
        and record.get("voice_sample_file") == relative
        and record.get("model") == MODEL_SOURCE
        and _valid_embedding(record.get("embedding")) is not None
    ):
        if record.get("name") != person.name or record.get("is_patient") != person.is_patient:
            record.update(name=person.name, is_patient=person.is_patient)
            _write_record(path, record)
        return result(True, "unchanged")

    try:
        audio, sample_rate = read_sample(person.voice_sample_file)
    except SampleError as error:
        return skip(str(error))

    try:
        embedding = embed(lazy_model.get(), audio, sample_rate)
    except Exception as error:  # noqa: BLE001 - any failure: no voiceprint, never a bad one
        log.exception("could not embed the voice sample of %s", person.name)
        return skip(f"could not embed: {error}")
    if _valid_embedding(embedding.tolist()) is None:
        return skip("could not embed: bad embedding")

    _write_record(
        path,
        {
            "person_id": person.id,
            "name": person.name,
            "is_patient": person.is_patient,
            "voice_sample_file": relative,
            "model": MODEL_SOURCE,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "embedding": [float(x) for x in embedding],
        },
    )
    log.info("made voiceprint for %s%s", person.name, " (patient)" if person.is_patient else "")
    return result(True, "made")


class SampleError(Exception):
    """The voice sample cannot give a trustworthy voiceprint."""


def read_sample(path: Path) -> tuple[np.ndarray, int]:
    """Mono float32 audio and its sample rate, or SampleError if it is unusable."""
    try:
        audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    except Exception as error:  # noqa: BLE001 - soundfile raises several kinds
        reason = str(error).replace(f"'{path}'", "").replace(str(path), "").strip(" :")
        raise SampleError(f"cannot read {Path(path).name} ({reason})") from error
    audio = audio.mean(axis=1)
    if audio.size == 0 or not np.all(np.isfinite(audio)):
        raise SampleError("unreadable audio")

    seconds = audio.size / sample_rate
    if seconds < MIN_SAMPLE_SECONDS:
        raise SampleError(f"too short ({seconds:.1f} s, need {MIN_SAMPLE_SECONDS:g} s)")

    level = _speech_level_dbfs(audio, sample_rate)
    if level < MIN_LEVEL_DBFS:
        raise SampleError(f"too quiet ({level:.0f} dBFS)")
    return audio, sample_rate


def _speech_level_dbfs(audio: np.ndarray, sample_rate: int) -> float:
    """95th percentile of 30 ms frame loudness, like the web's check."""
    frame = max(1, int(FRAME_SECONDS * sample_rate))
    count = audio.size // frame
    if count == 0:
        return -math.inf
    frames = audio[: count * frame].reshape(count, frame)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    db = 20 * np.log10(np.maximum(rms, 1e-10))
    return float(np.percentile(db, 95))


# Files ------------------------------------------------------------------------


def _voiceprint_path(data_dir: Path, person_id: str) -> Path:
    # people.id is a uuid; keep anything else from escaping the folder.
    safe = "".join(c for c in person_id if c.isalnum() or c == "-")
    return data_dir / VOICEPRINTS_NAME / f"{safe}.json"


def _relative(data_dir: Path, person: SyncedPerson) -> str:
    assert person.voice_sample_file is not None
    return person.voice_sample_file.relative_to(data_dir).as_posix()


def _valid_embedding(raw: Any) -> np.ndarray | None:
    try:
        embedding = np.asarray(raw, dtype=np.float32)
    except (TypeError, ValueError):
        return None
    if embedding.shape != (EMBEDDING_SIZE,) or not np.all(np.isfinite(embedding)):
        return None
    if abs(float(np.linalg.norm(embedding)) - 1.0) > 1e-3:
        return None
    return embedding


def _read_record(path: Path) -> dict[str, Any] | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        log.warning("could not read %s: %s", path.name, error)
        return None
    return record if isinstance(record, dict) else None


def _write_record(path: Path, record: dict[str, Any]) -> None:
    content = json.dumps(record, ensure_ascii=False).encode()
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=TEMP_SUFFIX)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp)
        raise


# Test entry -------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or refresh voiceprints from synced voice samples.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help=f"default {DATA_DIR}")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # model download requests

    results = refresh(args.data_dir)
    print(f"Voiceprints in {Path(args.data_dir).resolve() / VOICEPRINTS_NAME}:")
    if not results and not (Path(args.data_dir) / INDEX_NAME).is_file():
        print("  (nothing synced yet: run python -m argos_station.sync --once)")
    elif not results:
        print("  (nobody: sync found no people in Supabase)")
    for r in results:
        status = f"ok ({r.note})" if r.ok else f"skipped ({r.note})"
        print(f"  {r.name}: patient {'yes' if r.is_patient else 'no'}, {status}")


if __name__ == "__main__":
    main()
