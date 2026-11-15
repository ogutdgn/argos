"""Unit tests for argos_station/main.py: the wiring and the shutdown.

No mic, AirPod, model or Supabase: the listener is a fake that the test feeds
by hand, the recognizer is a fake that answers from a table, Supabase is a fake
that records its calls, and the processing endpoint is the local stand-in in
scripts/fake_process_endpoint.py. The tracker and recorder are the real ones.

Run from station/:

    .venv/bin/python -m unittest discover -s tests -v
"""

import json
import logging
import os
import signal
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from argos_station import main as station_main
from argos_station import sync
from argos_station.listener import FRAME_SAMPLES, SAMPLE_RATE, MicNotFoundError, SpeechClip
from argos_station.recognizer import Kind, Recognition
from argos_station.recorder import Recorder
from argos_station.tracker import END_AFTER_SECONDS, END_STATION_STOPPED, SAME_CONVERSATION_SECONDS, Timing

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fake_process_endpoint import FakeEndpoint  # noqa: E402

SECRET = "test-secret"  # a test value; the real one is only in .env

# Fictional demo family (the Odyssey).
ODYSSEUS = "11111111-1111-1111-1111-111111111111"
LAERTES = "33333333-3333-3333-3333-333333333333"
REMINDER = "44444444-4444-4444-4444-444444444444"


def setUpModule() -> None:
    logging.disable(logging.CRITICAL)


def tearDownModule() -> None:
    logging.disable(logging.NOTSET)


def wait_for(condition, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


# Fakes ------------------------------------------------------------------------


class Part:
    """Records start/stop into a shared list; can be told to fail."""

    def __init__(self, name: str, calls: list[str], fail_start: Exception | None = None,
                 fail_stop: Exception | None = None) -> None:
        self.name = name
        self.calls = calls
        self.fail_start = fail_start
        self.fail_stop = fail_stop

    def start(self) -> None:
        self.calls.append(f"start {self.name}")
        if self.fail_start:
            raise self.fail_start

    def stop(self, *args) -> None:
        self.calls.append(f"stop {self.name}")
        if self.fail_stop:
            raise self.fail_stop


class FakeListener:
    """Takes the same arguments as Listener; the test calls its callbacks."""

    def __init__(self, on_clip=None, on_audio=None, clip_seconds=4.0, mic_name=None, **_):
        self.on_clip = on_clip
        self.on_audio = on_audio
        self.clip_seconds = clip_seconds
        self.mic_name = mic_name
        self.running = False

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def speak(self, seconds: float = 4.0) -> None:
        """Mic frames for `seconds`, then the clip, as the listener sends them."""
        frames = [np.full(FRAME_SAMPLES, 0.1, dtype=np.float32)
                  for _ in range(round(seconds * SAMPLE_RATE / FRAME_SAMPLES))]
        for frame in frames:
            self.on_audio(frame)
        self.on_clip(SpeechClip(started_at=time.time(), audio=np.concatenate(frames)))


class FakeRecognizer:
    """Answers each clip with the next result in the list."""

    def __init__(self, *results: Recognition) -> None:
        self.results = list(results)

    def recognize(self, clip) -> Recognition:
        return self.results.pop(0)


class FakeSupabase:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.storage = self

    def from_(self, bucket: str):
        client = self

        class Bucket:
            def upload(self, path, file, options):
                client.calls.append(("upload", bucket, path))

        return Bucket()

    def table(self, name: str):
        client = self

        class Table:
            def upsert(self, rows, ignore_duplicates=False):
                client.calls.append(("upsert", name, rows))
                return self

            def execute(self):
                return None

        return Table()


VISITOR = Recognition(Kind.VISITOR, "match", person_id=ODYSSEUS, name="Odysseus", score=0.7)
UNKNOWN = Recognition(Kind.UNKNOWN, "below threshold")
PATIENT = Recognition(Kind.PATIENT, "patient")


# Start and stop order -----------------------------------------------------------


class StationOrder(unittest.TestCase):
    def station(self, calls, **fail) -> station_main.Station:
        def sync_loop(stop: threading.Event) -> None:
            calls.append("start sync")
            stop.wait()
            calls.append("stop sync")

        return station_main.Station(
            listener=Part("listener", calls, fail_start=fail.get("listener_start"),
                          fail_stop=fail.get("listener_stop")),
            tracker=Part("tracker", calls, fail_stop=fail.get("tracker_stop")),
            recorder=Part("recorder", calls),
            sync_loop=sync_loop,
        )

    def test_start_then_stop_in_a_safe_order(self):
        calls: list[str] = []
        station = self.station(calls)
        station.start()
        self.assertTrue(wait_for(lambda: "start sync" in calls))
        self.assertEqual(calls, ["start recorder", "start tracker", "start listener", "start sync"])
        calls.clear()
        station.stop()
        # Mic first, then the tracker (ends the conversation), then the recorder (uploads), then sync.
        self.assertEqual(calls, ["stop listener", "stop tracker", "stop recorder", "stop sync"])

    def test_stop_twice_is_harmless(self):
        calls: list[str] = []
        station = self.station(calls)
        station.start()
        station.stop()
        calls.clear()
        station.stop()
        self.assertEqual(calls, [])

    def test_a_failing_stop_does_not_skip_the_next_step(self):
        calls: list[str] = []
        station = self.station(calls, listener_stop=RuntimeError("mic gone"), tracker_stop=RuntimeError("boom"))
        station.start()
        self.assertTrue(wait_for(lambda: "start sync" in calls))
        calls.clear()
        station.stop()  # never raises
        self.assertEqual(calls, ["stop listener", "stop tracker", "stop recorder", "stop sync"])

    def test_mic_missing_stops_only_what_was_started(self):
        calls: list[str] = []
        station = self.station(calls, listener_start=MicNotFoundError("no mic"))
        with self.assertRaises(MicNotFoundError):
            station.start()
        calls.clear()
        station.stop()
        self.assertEqual(calls, ["stop tracker", "stop recorder"])

    def test_a_crashing_sync_loop_does_not_stop_the_station(self):
        calls: list[str] = []

        def broken(stop):
            raise RuntimeError("sync broke")

        station = station_main.Station(listener=Part("listener", calls), tracker=Part("tracker", calls),
                                       recorder=Part("recorder", calls), sync_loop=broken)
        station.start()
        station.stop()
        self.assertEqual(calls[-3:], ["stop listener", "stop tracker", "stop recorder"])


class ShutdownSignals(unittest.TestCase):
    def test_first_signal_asks_to_stop_second_quits(self):
        exits: list[int] = []
        shutdown = station_main.Shutdown(force_exit=exits.append)
        shutdown.handle(signal.SIGINT)
        self.assertTrue(shutdown.requested.is_set())
        self.assertEqual(exits, [])
        shutdown.handle(signal.SIGTERM)
        self.assertEqual(exits, [station_main.FORCE_EXIT_CODE])

    def test_sigterm_also_stops(self):
        shutdown = station_main.Shutdown(force_exit=lambda code: None)
        shutdown.handle(signal.SIGTERM)
        self.assertTrue(shutdown.requested.is_set())


# A whole conversation through the wiring -------------------------------------------


class FullConversation(unittest.TestCase):
    """Real tracker and recorder, wired by main.wire(), with a fake mic and recognizer."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        self.reminder_file = self.data / "reminder-audio" / ODYSSEUS / f"{REMINDER}.mp3"
        self.reminder_file.parent.mkdir(parents=True)
        self.reminder_file.write_bytes(b"not really audio")  # play is a fake
        index = {
            "synced_at": "2026-11-15T06:30:00+00:00",
            "people": [
                {"id": ODYSSEUS, "name": "Odysseus", "relationship": "son", "is_patient": False,
                 "voice_sample_file": None,
                 "reminder": {"id": REMINDER, "text": "This is Odysseus, your son.",
                              "created_at": "2026-11-15T06:00:00+00:00",
                              "audio_file": f"reminder-audio/{ODYSSEUS}/{REMINDER}.mp3"}},
                {"id": LAERTES, "name": "Laertes", "relationship": None, "is_patient": True,
                 "voice_sample_file": None, "reminder": None},
            ],
        }
        (self.data / sync.INDEX_NAME).write_text(json.dumps(index))
        self.played: list[Path] = []
        self.supabase = FakeSupabase()
        self.endpoint = FakeEndpoint(SECRET).start()

    def tearDown(self) -> None:
        self.endpoint.stop()
        self._tmp.cleanup()

    def station(self, *results: Recognition, timing: Timing = Timing()) -> station_main.Station:
        recorder = Recorder(data_dir=self.data, client=self.supabase, web_url=self.endpoint.url, secret=SECRET,
                            sleep=lambda s: None)

        def play(path: Path) -> bool:
            self.played.append(Path(path))
            return True

        return station_main.wire(
            FakeRecognizer(*results), recorder, timing=timing, play=play, data_dir=self.data,
            clip_seconds=4.0, mic_name="Test Mic", listener_class=FakeListener,
        )

    def test_listener_feeds_tracker_and_recorder(self):
        station = self.station()
        self.assertEqual(station.listener.on_clip, station.tracker.on_clip)
        self.assertEqual(station.listener.on_audio, station.recorder.on_audio)
        self.assertEqual(station.listener.mic_name, "Test Mic")
        self.assertEqual(station.tracker.hooks["start"], station.recorder.on_start)
        self.assertEqual(station.tracker.hooks["end"], station.recorder.on_end)

    def test_visitor_reminder_then_stop_uploads_and_calls_the_endpoint(self):
        station = self.station(VISITOR, VISITOR)
        station.start()
        station.listener.speak()
        self.assertTrue(wait_for(lambda: self.played))
        station.listener.speak()  # heard again: no second reminder
        self.assertTrue(wait_for(lambda: station.tracker.conversation is not None
                                 and station.tracker._clips.empty()))
        conversation = station.tracker.conversation
        station.stop()  # Ctrl+C mid-conversation

        self.assertEqual(self.played, [self.reminder_file.resolve()])
        steps = [(c[0], c[1]) for c in self.supabase.calls]
        self.assertEqual(steps, [("upload", "recordings"), ("upsert", "conversations"),
                                 ("upsert", "conversation_people")])
        self.assertEqual(self.supabase.calls[0][2], f"{conversation.id}.ogg")
        self.assertEqual(self.supabase.calls[2][2], [{"conversation_id": conversation.id, "person_id": ODYSSEUS}])
        self.assertEqual(len(self.endpoint.calls), 1)
        self.assertIn(conversation.id, self.endpoint.calls[0].body)
        self.assertEqual(list((self.data / "recordings").iterdir()), [])  # nothing left behind

    def test_station_stopped_is_the_end_reason(self):
        ended = []
        station = self.station(VISITOR)
        original = station.tracker.hooks["end"]
        station.tracker.hooks["end"] = lambda c: (ended.append(c.end_reason), original(c))
        station.start()
        station.listener.speak()
        self.assertTrue(wait_for(lambda: self.played))
        station.stop()
        self.assertEqual(ended, [END_STATION_STOPPED])

    def test_unknown_and_patient_voices_play_and_save_nothing(self):
        station = self.station(UNKNOWN, PATIENT)
        station.start()
        station.listener.speak()
        station.listener.speak()
        self.assertTrue(wait_for(lambda: station.tracker._clips.empty()))
        time.sleep(0.1)
        station.stop()
        self.assertEqual(self.played, [])
        self.assertEqual(self.supabase.calls, [])
        self.assertEqual(self.endpoint.calls, [])
        self.assertFalse((self.data / "recordings").exists())

    def test_pending_upload_from_an_earlier_run_is_handed_on_at_start(self):
        # An earlier run recorded a conversation but could not upload it.
        first = self.station(VISITOR)
        first.recorder._client_source = lambda: (_ for _ in ()).throw(RuntimeError("offline"))
        first.recorder.storage_tries = 1
        first.start()
        first.listener.speak()
        self.assertTrue(wait_for(lambda: self.played))
        first.stop()
        self.assertEqual(self.supabase.calls, [])
        self.assertEqual(len(list((self.data / "recordings").glob("*.json"))), 1)

        second = self.station()
        second.start()
        second.stop()  # waits for the upload
        self.assertEqual([c[0] for c in self.supabase.calls], ["upload", "upsert", "upsert"])
        self.assertEqual(len(self.endpoint.calls), 1)


# Arguments and env ---------------------------------------------------------------------


class Arguments(unittest.TestCase):
    def test_defaults_are_the_real_rules(self):
        args = station_main.parse_args([])
        self.assertEqual(args.timing.end_after, END_AFTER_SECONDS)
        self.assertEqual(args.timing.same_conversation_within, SAME_CONVERSATION_SECONDS)
        self.assertEqual(args.sync_interval, sync.SYNC_INTERVAL_SECONDS)
        self.assertFalse(args.dry_run)

    def test_shortened_timings_for_the_live_test(self):
        args = station_main.parse_args(["--end-after", "20", "--same-within", "60", "--dry-run"])
        self.assertEqual((args.timing.end_after, args.timing.same_conversation_within), (20, 60))
        self.assertTrue(args.dry_run)

    def test_bad_timing_is_refused(self):
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            station_main.parse_args(["--end-after", "60", "--same-within", "20"])


class Env(unittest.TestCase):
    def test_no_supabase_keys_exits_with_a_plain_message(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit) as caught:
            station_main.check_env()
        self.assertIsInstance(caught.exception.code, str)
        self.assertIn("SUPABASE_URL", caught.exception.code)
        self.assertIn("SUPABASE_SECRET_KEY", caught.exception.code)

    def test_no_web_url_only_warns(self):
        keys = {"SUPABASE_URL": "http://127.0.0.1:1", "SUPABASE_SECRET_KEY": "test"}
        with mock.patch.dict(os.environ, keys, clear=True), self.assertLogs("argos_station.main", "WARNING") as logs:
            logging.disable(logging.NOTSET)
            try:
                station_main.check_env()
            finally:
                logging.disable(logging.CRITICAL)
        self.assertTrue(any("ARGOS_WEB_URL" in line for line in logs.output))


class BackgroundSync(unittest.TestCase):
    def test_voiceprints_refresh_after_a_changed_pass(self):
        passes = [{"people": [{"id": "a"}]}, {"people": [{"id": "a"}]}, {"people": [{"id": "b"}]}]
        stop = threading.Event()
        changes = []

        def fake_sync_once(client, data_dir):
            index = passes.pop(0)
            if not passes:
                stop.set()
            return index

        with mock.patch.object(sync, "sync_once", fake_sync_once), mock.patch.object(sync, "describe", str):
            sync.run_forever(None, interval=0, stop=stop, on_change=changes.append)
        self.assertEqual(changes, [[{"id": "a"}], [{"id": "b"}]])

    def test_sync_loop_waits_one_interval_then_runs(self):
        stop = threading.Event()
        stop.set()
        with mock.patch.object(sync, "run_forever") as run_forever:
            station_main.make_sync_loop(None, Path("."), None, 30)(stop)
        run_forever.assert_not_called()  # stopped before the first background pass


if __name__ == "__main__":
    unittest.main()
