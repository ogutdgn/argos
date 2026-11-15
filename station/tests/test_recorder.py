"""Unit tests for argos_station/recorder.py.

No mic, AirPod, model or Supabase: audio frames are made by hand, Supabase is a
fake that records its calls, and the processing endpoint is the local stand-in
in scripts/fake_process_endpoint.py (real HTTP on 127.0.0.1). The real W2.2
endpoint is not called. Waits between retries are recorded, not slept.

Run from station/:

    .venv/bin/python -m unittest discover -s tests -v
"""

import json
import logging
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from argos_station.listener import FRAME_SAMPLES, SAMPLE_RATE
from argos_station.recognizer import Kind, Recognition
from argos_station.recorder import (
    BUCKET,
    BUCKET_LIMIT_BYTES,
    ENDPOINT_BACKOFF_SECONDS,
    ENDPOINT_TRIES,
    GAVE_UP,
    MAX_RECORDING_SECONDS,
    NOTIFIED,
    REJECTED,
    STAGE_SAVED,
    STAGE_TOO_LARGE,
    STAGE_UPLOADED,
    Job,
    Recorder,
)
from argos_station.tracker import END_STATION_STOPPED, Conversation, Tracker, Visitor

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fake_process_endpoint import FakeEndpoint  # noqa: E402

SECRET = "test-secret"  # a test value; the real one is only in .env
T0 = 1_800_000_000.0

# Fictional demo family (the Odyssey).
ODYSSEUS = "11111111-1111-1111-1111-111111111111"
PENELOPE = "22222222-2222-2222-2222-222222222222"
CONVERSATION = "6f1c1b8e-0c5e-4a39-9a43-2d0e3f6a7b10"


def setUpModule() -> None:
    logging.disable(logging.CRITICAL)


def tearDownModule() -> None:
    logging.disable(logging.NOTSET)


# Fakes ------------------------------------------------------------------------


class FakeSupabase:
    """Just enough of supabase.Client: storage upload and table upsert. Records every call in order."""

    def __init__(self, fail_upload: int = 0, fail_insert: int = 0) -> None:
        self.calls: list[tuple] = []
        self.fail_upload = fail_upload  # fail this many uploads first
        self.fail_insert = fail_insert
        self.storage = self
        self.uploaded: dict[str, bytes] = {}

    def from_(self, bucket: str):
        client = self

        class Bucket:
            def upload(self, path, file, options):
                client.calls.append(("upload", bucket, path, options))
                if client.fail_upload:
                    client.fail_upload -= 1
                    raise RuntimeError("storage is down")
                client.uploaded[path] = Path(file).read_bytes()

        return Bucket()

    def table(self, name: str):
        client = self

        class Table:
            def upsert(self, rows, ignore_duplicates=False):
                client.calls.append(("upsert", name, rows, ignore_duplicates))
                if client.fail_insert:
                    client.fail_insert -= 1
                    raise RuntimeError("database is down")
                return self

            def execute(self):
                return None

        return Table()

    def steps(self) -> list[str]:
        return [f"{c[0]} {c[1]}" for c in self.calls]


def noise(seconds: float, level: float = 0.3, seed: int = 0) -> list[np.ndarray]:
    """Frames like the listener's: FRAME_SAMPLES float32 samples each."""
    rng = np.random.default_rng(seed)
    count = round(seconds * SAMPLE_RATE / FRAME_SAMPLES)
    return [
        np.clip(level * rng.standard_normal(FRAME_SAMPLES), -1, 1).astype(np.float32) for _ in range(count)
    ]


def conversation(ended: bool = False, reason: str | None = None) -> Conversation:
    visitors = (
        Visitor(ODYSSEUS, "Odysseus", T0, T0 + 50, True),
        Visitor(PENELOPE, "Penelope", T0 + 10, T0 + 60, True),
    )
    return Conversation(
        id=CONVERSATION,
        started_at=T0,
        last_heard_at=T0 + 60,
        visitors=visitors,
        away=ended,
        ended_at=T0 + 60 if ended else None,
        end_reason=reason,
    )


class RecorderTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        self.supabase = FakeSupabase()
        self.sleeps: list[float] = []
        self.endpoint = FakeEndpoint(SECRET).start()

    def tearDown(self) -> None:
        self.endpoint.stop()
        self._tmp.cleanup()

    def recorder(self, **kwargs) -> Recorder:
        options = dict(
            data_dir=self.data,
            client=self.supabase,
            web_url=self.endpoint.url,
            secret=SECRET,
            pre_roll_seconds=2.0,
            sleep=self.sleeps.append,
        )
        options.update(kwargs)
        return Recorder(**options)

    def feed(self, recorder: Recorder, seconds: float, **kwargs) -> None:
        for frame in noise(seconds, **kwargs):
            recorder.on_audio(frame)

    def record(self, recorder: Recorder, before: float = 5.0, during: float = 3.0, reason="not heard") -> None:
        """Audio before the start, a conversation, audio during it, the end (queued, not processed)."""
        self.feed(recorder, before)
        recorder.on_start(conversation())
        self.feed(recorder, during)
        recorder.on_end(conversation(ended=True, reason=reason))

    def local(self, suffix: str) -> Path:
        return self.data / "recordings" / f"{CONVERSATION}.{suffix}"

    def recorded_seconds(self) -> float:
        info = sf.info(str(self.local("ogg")))
        self.assertEqual(info.samplerate, SAMPLE_RATE)
        self.assertEqual(info.channels, 1)
        return info.frames / info.samplerate


# What goes in the recording ----------------------------------------------------------


class WhatIsRecorded(RecorderTest):
    def test_no_conversation_nothing_recorded(self):
        # Unknown voices or the patient alone: the tracker never starts a conversation.
        recorder = self.recorder()
        self.feed(recorder, 5)
        recorder.start()
        recorder.stop()
        self.assertFalse((self.data / "recordings").exists() and any((self.data / "recordings").iterdir()))
        self.assertEqual(self.supabase.calls, [])
        self.assertEqual(self.endpoint.calls, [])

    def test_pre_roll_then_conversation(self):
        recorder = self.recorder(keep_local=True)
        self.record(recorder, before=5, during=3)
        # 2 s of the 5 s before the start (pre-roll), then 3 s.
        self.assertAlmostEqual(self.recorded_seconds(), 5.0, delta=0.1)
        job = Job.from_json(self.local("json").read_text())
        self.assertAlmostEqual(job.seconds, self.recorded_seconds(), delta=0.01)

    def test_away_gap_is_cut_and_return_gets_pre_roll(self):
        recorder = self.recorder()
        self.feed(recorder, 4)
        recorder.on_start(conversation())  # + 2 s pre-roll
        self.feed(recorder, 3)  # + 3 s
        recorder.on_away(conversation())
        self.feed(recorder, 20)  # not kept, except the last 2 s
        recorder.on_return(conversation())  # + 2 s pre-roll before the return
        self.feed(recorder, 3)  # + 3 s
        recorder.on_end(conversation(ended=True))
        self.assertAlmostEqual(self.recorded_seconds(), 10.0, delta=0.1)

    def test_short_away_never_writes_a_frame_twice(self):
        recorder = self.recorder()
        recorder.on_start(conversation())
        self.feed(recorder, 3)
        recorder.on_away(conversation())
        self.feed(recorder, 1)  # shorter than the pre-roll
        recorder.on_return(conversation())
        recorder.on_end(conversation(ended=True))
        self.assertAlmostEqual(self.recorded_seconds(), 4.0, delta=0.1)

    def test_recording_stops_at_max_length(self):
        recorder = self.recorder(max_seconds=3.0)
        self.record(recorder, before=1, during=10)
        self.assertAlmostEqual(self.recorded_seconds(), 3.0, delta=0.05)

    def test_end_of_another_conversation_is_ignored(self):
        recorder = self.recorder()
        recorder.on_start(conversation())
        other = Conversation(id="99999999-9999-9999-9999-999999999999", started_at=T0, last_heard_at=T0,
                             ended_at=T0, end_reason="not heard")
        recorder.on_end(other)
        self.assertFalse(self.local("json").exists())


class Encoding(RecorderTest):
    def test_ogg_opus_16k_mono(self):
        recorder = self.recorder(keep_local=True)
        self.record(recorder)
        recorder.process(CONVERSATION)
        kept = self.data / "recordings" / f"{CONVERSATION}.kept.ogg"
        info = sf.info(str(kept))
        self.assertEqual((info.format, info.subtype, info.samplerate, info.channels), ("OGG", "OPUS", 16000, 1))
        self.assertEqual(self.supabase.uploaded[f"{CONVERSATION}.ogg"], kept.read_bytes())

    def test_four_hours_fit_the_bucket_limit(self):
        # Full-level noise is the worst case for the encoder; speech and silence come out smaller.
        recorder = self.recorder(pre_roll_seconds=0.1, keep_local=True)
        recorder.on_start(conversation())
        self.feed(recorder, 60, level=0.9)
        recorder.on_end(conversation(ended=True))
        bytes_per_second = self.local("ogg").stat().st_size / 60
        self.assertLess(bytes_per_second * 8 / 1000, 26.0)  # kbps
        self.assertLess(bytes_per_second * MAX_RECORDING_SECONDS, BUCKET_LIMIT_BYTES)

    def test_over_the_size_limit_is_not_uploaded(self):
        recorder = self.recorder(size_limit=1000)
        self.record(recorder)
        self.assertIsNone(recorder.process(CONVERSATION))
        self.assertEqual(self.supabase.calls, [])
        self.assertTrue(self.local("ogg").exists())
        self.assertEqual(Job.from_json(self.local("json").read_text()).stage, STAGE_TOO_LARGE)
        self.assertEqual(recorder.pending(), [])  # not retried on every start


# Handing on: upload → rows → endpoint ------------------------------------------------


class HandingOn(RecorderTest):
    def test_upload_rows_endpoint_in_order(self):
        recorder = self.recorder()
        self.record(recorder)
        self.assertEqual(recorder.process(CONVERSATION), NOTIFIED)

        self.assertEqual(self.supabase.steps(),
                         ["upload recordings", "upsert conversations", "upsert conversation_people"])
        _, bucket, path, options = self.supabase.calls[0]
        self.assertEqual((bucket, path), (BUCKET, f"{CONVERSATION}.ogg"))
        self.assertEqual(options, {"content-type": "audio/ogg", "upsert": "true"})

        _, _, row, ignore = self.supabase.calls[1]
        self.assertTrue(ignore)
        self.assertEqual(row, {
            "id": CONVERSATION,
            "started_at": "2027-01-15T08:00:00+00:00",
            "ended_at": "2027-01-15T08:01:00+00:00",
            "recording_path": f"{CONVERSATION}.ogg",
            "status": "uploaded",
        })
        _, _, people, ignore = self.supabase.calls[2]
        self.assertTrue(ignore)
        self.assertEqual(people, [
            {"conversation_id": CONVERSATION, "person_id": ODYSSEUS},
            {"conversation_id": CONVERSATION, "person_id": PENELOPE},
        ])

        (call,) = self.endpoint.calls
        self.assertEqual(call.authorization, f"Bearer {SECRET}")
        self.assertEqual(json.loads(call.body), {"conversation_id": CONVERSATION})
        self.assertEqual(call.status, 202)
        # Done: nothing left locally.
        self.assertFalse(self.local("ogg").exists())
        self.assertFalse(self.local("json").exists())

    def test_upload_fails_no_rows_kept_locally_then_retried(self):
        self.supabase.fail_upload = 99
        recorder = self.recorder()
        self.record(recorder)
        self.assertIsNone(recorder.process(CONVERSATION))
        self.assertEqual(self.supabase.steps(), ["upload recordings"] * 3)  # STORAGE_TRIES, no rows
        self.assertEqual(self.endpoint.calls, [])
        self.assertTrue(self.local("ogg").exists())
        self.assertTrue(self.local("json").exists())

        # Next start: it goes through.
        self.supabase.fail_upload = 0
        self.supabase.calls.clear()
        recorder = self.recorder()
        self.assertEqual(recorder.pending(), [CONVERSATION])
        recorder.start()
        recorder.stop()
        self.assertEqual(self.supabase.steps(), ["upload recordings", "upsert conversations",
                                                 "upsert conversation_people"])
        self.assertEqual(len(self.endpoint.calls), 1)
        self.assertFalse(self.local("json").exists())

    def test_upload_retried_once_then_works(self):
        self.supabase.fail_upload = 1
        recorder = self.recorder()
        self.record(recorder)
        self.assertEqual(recorder.process(CONVERSATION), NOTIFIED)
        self.assertEqual(self.supabase.steps()[:2], ["upload recordings", "upload recordings"])
        self.assertEqual(self.sleeps, [2.0])

    def test_insert_fails_endpoint_not_called_upload_not_repeated(self):
        self.supabase.fail_insert = 99
        recorder = self.recorder()
        self.record(recorder)
        self.assertIsNone(recorder.process(CONVERSATION))
        self.assertEqual(self.endpoint.calls, [])
        self.assertEqual(Job.from_json(self.local("json").read_text()).stage, STAGE_UPLOADED)
        self.assertTrue(self.local("ogg").exists())

        self.supabase.fail_insert = 0
        self.supabase.calls.clear()
        self.assertEqual(recorder.process(CONVERSATION), NOTIFIED)
        self.assertEqual(self.supabase.steps(), ["upsert conversations", "upsert conversation_people"])

    def test_station_stopped_is_uploaded_and_stop_waits(self):
        recorder = self.recorder()
        recorder.start()
        self.record(recorder, reason=END_STATION_STOPPED)
        recorder.stop()
        self.assertEqual(len(self.supabase.uploaded), 1)
        self.assertEqual(len(self.endpoint.calls), 1)

    def test_with_the_real_tracker(self):
        # The hooks fit the tracker's: a recognized visitor starts it, end_now() hands it on.
        recorder = self.recorder()
        tracker = Tracker(on_start=recorder.on_start, on_away=recorder.on_away, on_return=recorder.on_return,
                          on_end=recorder.on_end, play=lambda path: True, people=lambda: [])
        recorder.start()
        self.feed(recorder, 3)
        tracker.heard(Recognition(Kind.UNKNOWN, "below threshold"), at=T0)
        self.assertFalse((self.data / "recordings").exists())  # unknown voice: nothing
        tracker.heard(Recognition(Kind.VISITOR, "match", person_id=ODYSSEUS, name="Odysseus", score=0.7), at=T0)
        self.feed(recorder, 2)
        tracker.end_now()
        recorder.stop()
        self.assertEqual(self.supabase.calls[2][2], [{"conversation_id": tracker_id(self), "person_id": ODYSSEUS}])
        self.assertEqual(len(self.endpoint.calls), 1)


def tracker_id(test: RecorderTest) -> str:
    return test.supabase.calls[1][2]["id"]


# The processing endpoint ---------------------------------------------------------------


class Endpoint(RecorderTest):
    def notify(self, *statuses: int, **kwargs) -> str:
        self.endpoint.statuses.clear()
        self.endpoint.statuses.extend(statuses)
        return self.recorder(**kwargs).notify(CONVERSATION)

    def test_202_and_200_are_done(self):
        self.assertEqual(self.notify(202), NOTIFIED)
        self.assertEqual(self.notify(200), NOTIFIED)
        self.assertEqual(len(self.endpoint.calls), 2)
        self.assertEqual(self.sleeps, [])

    def test_5xx_retried_with_backoff(self):
        self.assertEqual(self.notify(500, 503, 202), NOTIFIED)
        self.assertEqual([c.status for c in self.endpoint.calls], [500, 503, 202])
        self.assertEqual(self.sleeps, [2.0, 4.0])

    def test_5xx_gives_up_after_the_last_try(self):
        self.assertEqual(self.notify(500), GAVE_UP)
        self.assertEqual(len(self.endpoint.calls), ENDPOINT_TRIES)
        self.assertEqual(tuple(self.sleeps), ENDPOINT_BACKOFF_SECONDS)

    def test_4xx_never_retried(self):
        for status in (400, 404):
            self.endpoint.calls.clear()
            self.assertEqual(self.notify(status), REJECTED)
            self.assertEqual(len(self.endpoint.calls), 1)
        self.assertEqual(self.sleeps, [])

    def test_wrong_secret_is_401_not_retried(self):
        self.assertEqual(self.notify(202, secret="wrong"), REJECTED)
        self.assertEqual([c.status for c in self.endpoint.calls], [401])

    def test_network_error_retried_then_gives_up(self):
        self.endpoint.stop()
        dead = self.endpoint.url
        self.endpoint = FakeEndpoint(SECRET).start()  # for tearDown
        self.assertEqual(self.recorder(web_url=dead, endpoint_tries=3).notify(CONVERSATION), GAVE_UP)
        self.assertEqual(self.sleeps, [2.0, 4.0])

    def test_missing_url_or_secret_no_call(self):
        self.assertEqual(self.notify(202, web_url=""), GAVE_UP)
        self.assertEqual(self.notify(202, secret=""), GAVE_UP)
        self.assertEqual(self.endpoint.calls, [])

    def test_gave_up_keeps_the_job_without_audio(self):
        self.endpoint.statuses.clear()
        self.endpoint.statuses.append(500)
        recorder = self.recorder()
        self.record(recorder)
        self.assertEqual(recorder.process(CONVERSATION), GAVE_UP)
        self.assertFalse(self.local("ogg").exists())  # safe in storage
        self.assertEqual(Job.from_json(self.local("json").read_text()).stage, STAGE_SAVED)

        # Next start: only the endpoint is called again, no new upload or rows.
        self.endpoint.statuses[0] = 202
        self.supabase.calls.clear()
        self.assertEqual(recorder.process(CONVERSATION), NOTIFIED)
        self.assertEqual(self.supabase.calls, [])
        self.assertFalse(self.local("json").exists())

    def test_rejected_drops_the_job(self):
        self.endpoint.statuses.clear()
        self.endpoint.statuses.append(404)
        recorder = self.recorder()
        self.record(recorder)
        self.assertEqual(recorder.process(CONVERSATION), REJECTED)
        self.assertFalse(self.local("json").exists())
        self.assertEqual(recorder.pending(), [])


# Silence over mistakes ------------------------------------------------------------------


class NeverRaises(RecorderTest):
    def test_no_supabase_keys_keeps_the_job(self):
        def no_client():
            raise RuntimeError("missing in .env: SUPABASE_URL")

        recorder = self.recorder(client=no_client)
        self.record(recorder)
        self.assertIsNone(recorder.process(CONVERSATION))
        self.assertTrue(self.local("json").exists())

    def test_bad_frame_fails_the_recording_quietly(self):
        recorder = self.recorder()
        recorder.on_start(conversation())
        recorder.on_audio(object())  # not audio
        self.feed(recorder, 1)
        recorder.on_end(conversation(ended=True))
        self.assertFalse(self.local("json").exists())  # not uploaded
        self.assertEqual(self.supabase.calls, [])

    def test_cannot_open_the_file(self):
        (self.data / "recordings").write_text("a file where the folder should be")
        recorder = self.recorder()
        recorder.on_start(conversation())  # logged, not raised
        self.feed(recorder, 1)
        recorder.on_end(conversation(ended=True))
        self.assertEqual(self.supabase.calls, [])

    def test_unreadable_job_file_left_alone(self):
        folder = self.data / "recordings"
        folder.mkdir()
        (folder / f"{CONVERSATION}.json").write_text("{not json")
        recorder = self.recorder()
        self.assertEqual(recorder.pending(), [])
        self.assertIsNone(recorder.process(CONVERSATION))


if __name__ == "__main__":
    unittest.main()
