"""Starts the whole patient station with one command.

Run from ``station/``::

    .venv/bin/python -m argos_station.main

This file only wires the modules together; the rules live in them.

Start-up, in order:

1. Read ``.env``. No ``SUPABASE_URL`` or ``SUPABASE_SECRET_KEY``: exit with a
   plain message (nothing can be synced or uploaded). No ``ARGOS_WEB_URL`` or
   ``STATION_API_SECRET``: a warning; conversations are still recorded and
   uploaded, and the endpoint call waits for the next start (recorder.py).
2. Check the AirPod is connected. If not, log it: reminders stay silent until
   the station is restarted with the AirPod connected (docs/edge-cases.md,
   "AirPod connected after the station starts"). Never the MacBook speakers.
3. Load the speaker model once; the recognizer and the voiceprint refresh
   share it.
4. One sync pass, then a voiceprint refresh. If Supabase cannot be reached,
   the station goes on with what was synced before.
5. Start the recorder (it hands on what an earlier run left), the tracker,
   the listener (exit if the MacBook mic is missing) and the background sync
   (every ``SYNC_INTERVAL_SECONDS``; voiceprints are refreshed after each pass
   that changed the people). The recognizer picks up new voiceprints on its own.

Wiring: listener ``on_clip`` → tracker (recognizer → reminder into the AirPod
through the player); listener ``on_audio`` → recorder; tracker hooks →
recorder.

Stopping (Ctrl+C or SIGTERM), in order: the listener (mic closed, nothing new
comes in), the tracker (an open conversation ends as "station stopped"), the
recorder (waits up to 2 min for uploads in flight), then the background sync.
A second Ctrl+C quits at once; what was not handed on stays in
``data/recordings/`` and is tried again on the next start.

Errors: each module logs its own and keeps going (silence over mistakes); a
failing step at shutdown is logged and the next step still runs.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from argos_station import sync, voiceprints
from argos_station.config import REQUIRED_KEYS, connect, load_env
from argos_station.listener import DEFAULT_CLIP_SECONDS, Listener, MicNotFoundError
from argos_station.recognizer import Recognizer
from argos_station.recorder import STOP_WAIT_SECONDS, Recorder
from argos_station.sync import DATA_DIR, SYNC_INTERVAL_SECONDS
from argos_station.tracker import (
    END_AFTER_SECONDS,
    REMINDER_PAUSE_SECONDS,
    SAME_CONVERSATION_SECONDS,
    Timing,
    Tracker,
)

log = logging.getLogger("argos_station.main")

ENDPOINT_KEYS = ("ARGOS_WEB_URL", "STATION_API_SECRET")
SYNC_STOP_WAIT_SECONDS = 15.0  # a sync pass in progress may be mid-download; files are written whole
FORCE_EXIT_CODE = 130


class _Part(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...


# Stopping ------------------------------------------------------------------------


class Shutdown:
    """Ctrl+C and SIGTERM: the first asks the station to stop, the second quits at once."""

    def __init__(self, force_exit: Callable[[int], Any] = os._exit) -> None:
        self.requested = threading.Event()
        self._force_exit = force_exit

    def install(self) -> None:
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, self.handle)

    def handle(self, signum: int, _frame: Any = None) -> None:
        name = signal.Signals(signum).name
        if self.requested.is_set():
            log.warning("%s again: quitting now. Unfinished uploads are tried again on the next start.", name)
            logging.shutdown()
            self._force_exit(FORCE_EXIT_CODE)
            return
        self.requested.set()
        log.info("%s: stopping the station (Ctrl+C again to quit at once)", name)


class Station:
    """The running parts, started and stopped in a safe order."""

    def __init__(
        self,
        *,
        listener: _Part,
        tracker: _Part,
        recorder: Any,  # Recorder: stop(timeout)
        sync_loop: Callable[[threading.Event], None] | None = None,
        recorder_wait: float = STOP_WAIT_SECONDS,
        sync_wait: float = SYNC_STOP_WAIT_SECONDS,
    ) -> None:
        self.listener = listener
        self.tracker = tracker
        self.recorder = recorder
        self.sync_loop = sync_loop
        self.recorder_wait = recorder_wait
        self.sync_wait = sync_wait
        self.sync_stop = threading.Event()
        self._sync_thread: threading.Thread | None = None
        self._started: list[str] = []

    def start(self) -> None:
        """Recorder, tracker, listener, then the background sync. Raises if the listener cannot start."""
        self.recorder.start()
        self._started.append("recorder")
        self.tracker.start()
        self._started.append("tracker")
        self.listener.start()  # MicNotFoundError: the caller calls stop()
        self._started.append("listener")
        if self.sync_loop is not None:
            self._sync_thread = threading.Thread(target=self._run_sync, name="sync", daemon=True)
            self._sync_thread.start()
            self._started.append("sync")

    def stop(self) -> None:
        """Stop what was started: listener, tracker, recorder, sync. Never raises; safe to call twice."""
        started, self._started = self._started, []
        if "listener" in started:
            self._step("stop the listener", self.listener.stop)
        if "tracker" in started:
            self._step("stop the tracker", self.tracker.stop)  # an open conversation ends → recorder
        if "recorder" in started:
            log.info("stopping the recorder (waits up to %.0f s for uploads in flight)", self.recorder_wait)
            self._step("stop the recorder", lambda: self.recorder.stop(self.recorder_wait))
        if "sync" in started:
            self.sync_stop.set()
            if self._sync_thread is not None:
                self._sync_thread.join(self.sync_wait)
                if self._sync_thread.is_alive():
                    log.warning("sync pass still running after %.0f s; leaving it", self.sync_wait)
                self._sync_thread = None

    def _run_sync(self) -> None:
        assert self.sync_loop is not None
        try:
            self.sync_loop(self.sync_stop)
        except Exception:  # noqa: BLE001 - the station keeps going on what was synced
            log.exception("background sync stopped; using what was synced until the next start")

    @staticmethod
    def _step(what: str, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception:  # noqa: BLE001 - the next step still runs
            log.exception("could not %s", what)


# Wiring ----------------------------------------------------------------------------


def wire(
    recognizer: Any,
    recorder: Any,
    *,
    timing: Timing,
    play: Callable[[Path], bool],
    data_dir: Path = DATA_DIR,
    clip_seconds: float = DEFAULT_CLIP_SECONDS,
    mic_name: str | None = None,
    sync_loop: Callable[[threading.Event], None] | None = None,
    listener_class: Callable[..., _Part] = Listener,
) -> Station:
    """Connect listener → tracker → player and listener/tracker → recorder."""
    tracker = Tracker(
        recognizer,
        timing=timing,
        on_start=recorder.on_start,
        on_away=recorder.on_away,
        on_return=recorder.on_return,
        on_end=recorder.on_end,
        play=play,
        data_dir=data_dir,
    )
    listener = listener_class(
        on_clip=tracker.on_clip,
        on_audio=recorder.on_audio,
        clip_seconds=clip_seconds,
        mic_name=mic_name,
    )
    return Station(listener=listener, tracker=tracker, recorder=recorder, sync_loop=sync_loop)


def check_env() -> None:
    """Exit with a plain message without Supabase keys; warn without the endpoint keys."""
    missing = [key for key in REQUIRED_KEYS if not os.environ.get(key)]
    if missing:
        sys.exit(
            f"Missing in .env: {', '.join(missing)}. The station cannot run without Supabase "
            "(see station/CLAUDE.md, \"Run\")."
        )
    for key in ENDPOINT_KEYS:
        if not os.environ.get(key):
            log.warning(
                "%s is not set in .env: conversations are uploaded but not sent for processing "
                "(tried again on the next start)",
                key,
            )


def check_airpod(device_name: str | None) -> bool:
    """Log whether the AirPod is there. Devices are read once, so this is what the station will see."""
    try:
        from argos_station import player  # opens the audio system

        device = player.find_airpod(device_name)
        wanted = player.device_name_wanted(device_name)
    except Exception:  # noqa: BLE001
        log.exception("could not read the audio devices; reminders may stay silent")
        return False
    if device is None:
        log.error(
            "No AirPod found (no output device matching %r). Reminders stay silent until the station is "
            "restarted with the AirPod connected; they never play through the MacBook speakers.",
            wanted,
        )
        return False
    log.info("AirPod found: %r. Reminders play only there.", device["name"])
    return True


def make_play(device_name: str | None, dry_run: bool) -> Callable[[Path], bool]:
    if dry_run:
        def play(path: Path) -> bool:
            log.info("(dry run) would play %s", Path(path).name)
            return True
    else:
        from argos_station import player

        def play(path: Path) -> bool:
            return player.play(path, device_name)
    return play


def refresh_voiceprints(data_dir: Path, model: Any) -> None:
    """Bring the voiceprints in line with the last sync. Logged, never raised."""
    try:
        results = voiceprints.refresh(data_dir, model)
    except Exception:  # noqa: BLE001 - the recognizer keeps the voiceprints it has
        log.exception("could not refresh the voiceprints")
        return
    made = [r.name for r in results if r.note == "made"]
    if made:
        log.info("new voiceprints: %s", ", ".join(made))


def first_sync(client: Any, data_dir: Path) -> None:
    try:
        index = sync.sync_once(client, data_dir)
    except Exception as error:  # noqa: BLE001 - go on with the local copy
        log.warning("could not sync from Supabase (%s); using what was synced before", error)
        return
    log.info("synced %d people:\n%s", len(index["people"]), sync.describe(index["people"]))


def make_sync_loop(client: Any, data_dir: Path, model: Any, interval: float) -> Callable[[threading.Event], None]:
    def loop(stop: threading.Event) -> None:
        if stop.wait(interval):  # the first pass already ran at start-up
            return
        sync.run_forever(
            client,
            interval,
            data_dir,
            stop=stop,
            on_change=lambda _people: refresh_voiceprints(data_dir, model),
        )
    return loop


def describe_voiceprints(recognizer: Recognizer) -> None:
    known = recognizer.voiceprints
    if not known:
        log.warning("no voiceprints yet: the station recognizes nobody and stays silent")
        return
    log.info("knows %d voice(s): %s", len(known),
             ", ".join(vp.name + (" (patient)" if vp.is_patient else "") for vp in known))


# Entry -------------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m argos_station.main",
        description="Run the patient station: sync, voiceprints, listener, recognizer, tracker, player and "
        "recorder together. Ctrl+C to stop.",
    )
    parser.add_argument("--end-after", type=float, default=END_AFTER_SECONDS,
                        help=f"seconds without a visitor's voice before they count as away (default {END_AFTER_SECONDS})")
    parser.add_argument("--same-within", type=float, default=SAME_CONVERSATION_SECONDS,
                        help="seconds since last heard within which a return is the same conversation "
                             f"(default {SAME_CONVERSATION_SECONDS})")
    parser.add_argument("--pause", type=float, default=REMINDER_PAUSE_SECONDS,
                        help=f"seconds between two reminders (default {REMINDER_PAUSE_SECONDS:g})")
    parser.add_argument("--sync-interval", type=float, default=SYNC_INTERVAL_SECONDS,
                        help=f"seconds between sync passes (default {SYNC_INTERVAL_SECONDS})")
    parser.add_argument("--seconds", type=float, default=DEFAULT_CLIP_SECONDS,
                        help=f"clip length from the mic, 3-5 (default {DEFAULT_CLIP_SECONDS:g})")
    parser.add_argument("--mic", help="input device name (default: the MacBook's built-in mic)")
    parser.add_argument("--device", help="part of the AirPod's output name (default: $ARGOS_AIRPOD_NAME or 'AirPods')")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help=f"default {DATA_DIR}")
    parser.add_argument("--dry-run", action="store_true", help="log which reminder would play instead of playing it")
    parser.add_argument("--keep-local", action="store_true",
                        help="keep each recording after upload, as data/recordings/{id}.kept.ogg, to listen to it")
    parser.add_argument("--quiet", action="store_true", help="hide the recognizer's per-clip scores")
    args = parser.parse_args(argv)
    try:
        args.timing = Timing(args.end_after, args.same_within, args.pause)
    except ValueError as error:
        parser.error(str(error))
    if args.sync_interval <= 0:
        parser.error("--sync-interval must be above 0")
    if not 3.0 <= args.seconds <= 5.0:
        parser.error("--seconds must be between 3 and 5")
    return args


def run(args: argparse.Namespace, shutdown: Shutdown) -> int:
    """Start everything, wait for Ctrl+C, stop. Returns the exit code."""
    data_dir = Path(args.data_dir).resolve()
    client = connect()

    if args.dry_run:
        log.info("dry run: reminders are logged, not played")
    else:
        check_airpod(args.device)

    log.info("loading the speaker model (slow the first time)...")
    try:
        model = voiceprints.load_model(data_dir)
    except Exception as error:  # noqa: BLE001 - nobody can be recognized without it
        log.exception("could not load the speaker model")
        print(f"The station cannot run without the speaker model: {error}", file=sys.stderr)
        return 1
    if shutdown.requested.is_set():
        return 0

    first_sync(client, data_dir)
    refresh_voiceprints(data_dir, model)
    recognizer = Recognizer(data_dir, model=model)
    describe_voiceprints(recognizer)
    if shutdown.requested.is_set():
        return 0

    station = wire(
        recognizer,
        Recorder(data_dir=data_dir, keep_local=args.keep_local),
        timing=args.timing,
        play=make_play(args.device, args.dry_run),
        data_dir=data_dir,
        clip_seconds=args.seconds,
        mic_name=args.mic,
        sync_loop=make_sync_loop(client, data_dir, model, args.sync_interval),
    )
    try:
        station.start()
    except MicNotFoundError:
        station.stop()
        print("The station cannot run without the MacBook's built-in mic (see the log above).", file=sys.stderr)
        return 1
    except Exception:  # noqa: BLE001
        log.exception("the station could not start")
        station.stop()
        return 1

    timing = args.timing
    log.info(
        "station running: away after %.0f s without a visitor, same conversation within %.0f s, "
        "sync every %.0f s. Ctrl+C to stop.",
        timing.end_after,
        timing.same_conversation_within,
        args.sync_interval,
    )
    while not shutdown.requested.wait(0.5):
        pass
    station.stop()
    return 0


def main(argv: list[str] | None = None) -> None:
    shutdown = Shutdown()
    shutdown.install()
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.quiet:
        logging.getLogger("argos_station.recognizer").setLevel(logging.WARNING)

    load_env()
    check_env()
    code = run(args, shutdown)
    log.info("station stopped" if code == 0 else "station did not start")
    sys.exit(code)


if __name__ == "__main__":
    main()
