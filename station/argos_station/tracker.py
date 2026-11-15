"""Tracks conversations: when they start and end, and who gets a reminder.

The tracker takes the recognizer's answer for each speech clip and keeps one
conversation at a time:

- **Start.** A known visitor is recognized (``Kind.VISITOR``) and no
  conversation is open: a conversation starts, and that visitor's current
  reminder plays into the AirPod right away.
- **Once per person.** Each visitor gets one reminder per conversation. A
  second visitor recognized while the conversation is open joins it and gets
  their own reminder, after the first one with a short pause
  (``REMINDER_PAUSE_SECONDS``) in between.
- **Away.** When no visitor of the conversation has been heard for
  ``END_AFTER_SECONDS`` (5 min, docs/flows.md, Flow C), the visitors count as
  gone: ``on_away`` fires.
- **Return.** If one of them is heard again within
  ``SAME_CONVERSATION_SECONDS`` (30 min) of when they were last heard, it is
  the same conversation (docs/edge-cases.md, "Visitor leaves for a short
  time"): ``on_return`` fires and no reminder plays again.
- **End.** Once no visitor has been heard for ``SAME_CONVERSATION_SECONDS``,
  the conversation is over: ``on_end`` fires with ``ended_at`` set to when the
  visitors were last heard. A visitor who was not in it, heard while it is
  away, ends it at once and starts a new conversation.
- **Never for "patient" or "unknown".** Those results are ignored: they start
  nothing, play nothing, and do not count as a visitor being heard. So a
  conversation with only unknown voices never exists and is never saved.

Silence over mistakes: if a visitor has no reminder yet, the AirPod is not
there, the file is gone, or anything fails, nothing plays and it is logged.
There is one try per visitor per conversation; a reminder that did not play is
not tried again later in the same conversation.

All timing rules are in ``Timing`` (defaults from the constants below). Tests
and the test entry shorten them; ``clock`` and ``sleep`` can be swapped so unit
tests run without waiting.

For S2.2 (recorder) and S2.3 (main.py)
--------------------------------------

::

    from argos_station.tracker import Tracker

    tracker = Tracker(
        recognizer,                          # recognizer.Recognizer
        on_start=lambda conversation: ...,   # a conversation started: start recording
        on_away=lambda conversation: ...,    # 5 min without the visitors' voices
        on_return=lambda conversation: ...,  # one of them is back within 30 min
        on_end=lambda conversation: ...,     # over: upload, insert rows, call the endpoint
    )
    listener = Listener(on_clip=tracker.on_clip, ...)
    tracker.start()
    listener.start()
    ...
    listener.stop()
    tracker.stop()    # ends an open conversation (end_reason "station stopped")

Each hook gets a ``Conversation`` snapshot: ``id`` (a new uuid4, the
``conversations.id`` the station chooses), ``started_at``, ``last_heard_at``,
``ended_at`` (on_end only), ``end_reason``, and ``visitors`` (one ``Visitor``
per person heard: the ``conversation_people`` rows). Times are Unix seconds.
Hooks run on the tracker's threads, one at a time and in order (an ``on_end``
always comes before the next ``on_start``); an exception in a hook is logged
and the tracker keeps going. They run while the tracker holds its lock, so keep
them quick (hand uploads to your own thread). Reading ``tracker.conversation``
from a hook is fine.

Threads: ``on_clip`` only queues the clip. One worker recognizes clips (about
a second each), one plays reminders (``player.play`` blocks until the clip
ends), and one checks the timers every ``tick_seconds``.

Test entry (listener + recognizer + tracker + player)::

    python -m argos_station.tracker --end-after 20 --same-within 60
"""

from __future__ import annotations

import argparse
import logging
import queue
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from argos_station.recognizer import Kind, Recognition
from argos_station.sync import DATA_DIR, SyncedPerson, load_people

if TYPE_CHECKING:
    from argos_station.listener import SpeechClip
    from argos_station.recognizer import Recognizer

log = logging.getLogger(__name__)

# The timing rules, in one place (docs/flows.md, docs/edge-cases.md).
END_AFTER_SECONDS = 5 * 60  # Flow C: no visitor's voice this long → they are gone ("away").
SAME_CONVERSATION_SECONDS = 30 * 60  # Back within this long of last heard → same conversation.
REMINDER_PAUSE_SECONDS = 2.0  # Two visitors at once: silence between their reminders.
TICK_SECONDS = 1.0  # How often the timers are checked.

END_NOT_HEARD = "not heard"  # nobody back within SAME_CONVERSATION_SECONDS
END_NEW_VISITOR = "new visitor"  # someone new arrived while the visitors were away
END_STATION_STOPPED = "station stopped"  # tracker.stop() with a conversation open


@dataclass(frozen=True)
class Timing:
    end_after: float = END_AFTER_SECONDS
    same_conversation_within: float = SAME_CONVERSATION_SECONDS
    reminder_pause: float = REMINDER_PAUSE_SECONDS

    def __post_init__(self) -> None:
        if self.end_after <= 0:
            raise ValueError(f"end_after must be above 0, got {self.end_after}")
        if self.same_conversation_within < self.end_after:
            raise ValueError(
                f"same_conversation_within ({self.same_conversation_within}) must be at least "
                f"end_after ({self.end_after})"
            )
        if self.reminder_pause < 0:
            raise ValueError(f"reminder_pause must be 0 or more, got {self.reminder_pause}")


@dataclass(frozen=True)
class Visitor:
    person_id: str
    name: str
    first_heard_at: float
    last_heard_at: float
    reminder_played: bool | None = None  # None: not tried yet; False: tried, stayed silent


@dataclass(frozen=True)
class Conversation:
    id: str
    started_at: float
    last_heard_at: float  # last time any of its visitors was heard
    visitors: tuple[Visitor, ...] = ()
    away: bool = False  # no visitor heard for Timing.end_after
    ended_at: float | None = None  # set when it ends: = last_heard_at
    end_reason: str | None = None

    @property
    def person_ids(self) -> tuple[str, ...]:
        return tuple(v.person_id for v in self.visitors)

    def visitor(self, person_id: str) -> Visitor | None:
        return next((v for v in self.visitors if v.person_id == person_id), None)

    def describe(self) -> str:
        names = ", ".join(v.name for v in self.visitors) or "nobody"
        return f"{self.id[:8]} with {names}"


@dataclass(frozen=True)
class _Reminder:
    conversation_id: str
    person_id: str
    name: str
    audio_file: Path


Hook = Callable[[Conversation], None]


def _default_play(path: Path) -> bool:
    from argos_station import player  # Opens the audio system; only when something plays.

    return player.play(path)


class Tracker:
    """One conversation at a time: start, reminders, away, return, end."""

    def __init__(
        self,
        recognizer: Recognizer | None = None,
        *,
        timing: Timing = Timing(),
        on_start: Hook | None = None,
        on_away: Hook | None = None,
        on_return: Hook | None = None,
        on_end: Hook | None = None,
        play: Callable[[Path], bool] = _default_play,
        people: Callable[[], list[SyncedPerson]] | None = None,
        data_dir: Path = DATA_DIR,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        tick_seconds: float = TICK_SECONDS,
    ) -> None:
        self.recognizer = recognizer
        self.timing = timing
        self.hooks = {"start": on_start, "away": on_away, "return": on_return, "end": on_end}
        self.play = play
        self.people = people or (lambda: load_people(data_dir))
        self.clock = clock
        self.sleep = sleep
        self.tick_seconds = tick_seconds

        # Guards _conversation. Hooks run while it is held, so they come in order
        # (an end before the next start) and one at a time.
        self._lock = threading.RLock()
        self._conversation: Conversation | None = None
        self._clips: queue.Queue[SpeechClip] = queue.Queue()
        self._reminders: queue.Queue[_Reminder] = queue.Queue()
        self._last_reminder_end: float | None = None
        self._running = threading.Event()
        self._stopping = threading.Event()  # wakes the timer thread on stop()
        self._threads: list[threading.Thread] = []

    # Reading ---------------------------------------------------------------

    @property
    def conversation(self) -> Conversation | None:
        """The open conversation (possibly away), or None."""
        with self._lock:
            return self._conversation

    # Input -------------------------------------------------------------------

    def on_clip(self, clip: SpeechClip) -> None:
        """Listener callback: queue the clip for recognition and return at once."""
        if self._running.is_set():
            self._clips.put(clip)

    def heard(self, result: Recognition, at: float | None = None) -> None:
        """Act on one recognition result. ``at``: when (Unix time), default now. Never raises."""
        with self._lock:
            events: list[tuple[str, Conversation]] = []
            try:
                now = self.clock() if at is None else at
                events += self._expire(now)
                if result.kind is Kind.VISITOR and result.person_id:
                    events += self._visitor_heard(result.person_id, result.name or "?", now)
                # Patient or unknown: nothing starts, nothing plays, nobody counts as heard.
            except Exception:  # noqa: BLE001 - silence over mistakes
                log.exception("tracker could not handle a recognition; playing nothing")
            self._fire(events)

    def tick(self, now: float | None = None) -> None:
        """Check the timers: away after end_after, end after same_conversation_within."""
        with self._lock:
            events: list[tuple[str, Conversation]] = []
            try:
                events += self._expire(self.clock() if now is None else now)
            except Exception:  # noqa: BLE001
                log.exception("tracker timer check failed")
            self._fire(events)

    def end_now(self, reason: str = END_STATION_STOPPED) -> None:
        """End the open conversation now (if any), as if its visitors had left."""
        with self._lock:
            self._fire(self._end(reason) if self._conversation else [])

    # Threads -----------------------------------------------------------------

    def start(self) -> None:
        if self._running.is_set():
            return
        self._running.set()
        self._stopping.clear()
        self._threads = [
            threading.Thread(target=loop, name=f"tracker-{name}", daemon=True)
            for name, loop in (
                ("recognize", self._recognize_loop),
                ("remind", self._remind_loop),
                ("timer", self._timer_loop),
            )
        ]
        for thread in self._threads:
            thread.start()
        log.info(
            "tracker started: away after %.0f s, same conversation within %.0f s, %.1f s between reminders",
            self.timing.end_after,
            self.timing.same_conversation_within,
            self.timing.reminder_pause,
        )

    def stop(self) -> None:
        """Stop the threads and end an open conversation (end_reason "station stopped")."""
        if not self._running.is_set():
            return
        self._running.clear()
        self._stopping.set()
        for thread in self._threads:
            thread.join(timeout=10)
        self._threads = []
        self.end_now(END_STATION_STOPPED)

    def __enter__(self) -> Tracker:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def play_pending(self) -> None:
        """Play every queued reminder now, on this thread (for tests; start() does it on its own)."""
        while True:
            try:
                reminder = self._reminders.get_nowait()
            except queue.Empty:
                return
            self._play_one(reminder)

    def _recognize_loop(self) -> None:
        while self._running.is_set():
            try:
                clip = self._clips.get(timeout=0.25)
            except queue.Empty:
                continue
            if self.recognizer is None:
                log.error("tracker has no recognizer; ignoring the clip")
                continue
            self.heard(self.recognizer.recognize(clip))  # recognize() never raises

    def _remind_loop(self) -> None:
        while self._running.is_set():
            try:
                reminder = self._reminders.get(timeout=0.25)
            except queue.Empty:
                continue
            self._play_one(reminder)

    def _timer_loop(self) -> None:
        while self._running.is_set():
            self.tick()
            self._stopping.wait(self.tick_seconds)

    # Rules (inside self._lock) -------------------------------------------------

    def _expire(self, now: float) -> list[tuple[str, Conversation]]:
        conversation = self._conversation
        if conversation is None:
            return []
        silent_for = now - conversation.last_heard_at
        if silent_for >= self.timing.same_conversation_within:
            return self._end(END_NOT_HEARD)
        if silent_for >= self.timing.end_after and not conversation.away:
            self._conversation = replace(conversation, away=True)
            log.info(
                "conversation %s: visitors not heard for %.0f s; away (same conversation if back within %.0f s)",
                conversation.describe(),
                silent_for,
                self.timing.same_conversation_within,
            )
            return [("away", self._conversation)]
        return []

    def _visitor_heard(self, person_id: str, name: str, now: float) -> list[tuple[str, Conversation]]:
        events: list[tuple[str, Conversation]] = []
        conversation = self._conversation

        if conversation is not None and conversation.away and conversation.visitor(person_id) is None:
            # Someone new while the others are gone: that conversation is over.
            events += self._end(END_NEW_VISITOR)
            conversation = None

        if conversation is None:
            conversation = Conversation(id=str(uuid.uuid4()), started_at=now, last_heard_at=now)
            self._conversation = conversation
            log.info("conversation %s started: %s recognized", conversation.id[:8], name)
            events.append(("start", conversation))
        elif conversation.away:
            log.info("conversation %s: %s is back; same conversation, no new reminder", conversation.describe(), name)
            conversation = replace(conversation, away=False)
            events.append(("return", conversation))

        visitor = conversation.visitor(person_id)
        if visitor is None:
            visitor = Visitor(person_id, name, first_heard_at=now, last_heard_at=now)
            if conversation.visitors:
                log.info("conversation %s: %s joined", conversation.describe(), name)
            conversation = replace(conversation, visitors=(*conversation.visitors, visitor))
            self._conversation = conversation
            self._queue_reminder(conversation, visitor)
            conversation = self._conversation
        else:
            visitor = replace(visitor, last_heard_at=now)
            conversation = self._with_visitor(conversation, visitor)

        self._conversation = replace(conversation, last_heard_at=max(conversation.last_heard_at, now))
        # Hooks get the state after this hearing.
        return [(kind, self._conversation if kind != "end" else snapshot) for kind, snapshot in events]

    def _queue_reminder(self, conversation: Conversation, visitor: Visitor) -> None:
        """Queue this visitor's one reminder for this conversation, or record that it stays silent."""
        reminder = None
        try:
            person = next((p for p in self.people() if p.id == visitor.person_id), None)
            if person is None:
                log.warning("no synced person for %s (%s); playing nothing", visitor.name, visitor.person_id)
            elif person.is_patient:
                log.error("%s is the patient in the synced people; playing nothing", visitor.name)
            elif person.reminder is None:
                log.warning("%s has no reminder audio yet; playing nothing", visitor.name)
            else:
                reminder = person.reminder
        except Exception:  # noqa: BLE001 - silence over mistakes
            log.exception("could not read the reminder for %s; playing nothing", visitor.name)

        if reminder is None:
            self._conversation = self._with_visitor(conversation, replace(visitor, reminder_played=False))
            return
        log.info("reminder for %s queued (%s)", visitor.name, reminder.audio_file.name)
        self._reminders.put(_Reminder(conversation.id, visitor.person_id, visitor.name, reminder.audio_file))

    def _end(self, reason: str) -> list[tuple[str, Conversation]]:
        conversation = self._conversation
        assert conversation is not None
        ended = replace(conversation, away=True, ended_at=conversation.last_heard_at, end_reason=reason)
        self._conversation = None
        log.info(
            "conversation %s ended (%s): %.0f s from start to last heard",
            ended.describe(),
            reason,
            ended.ended_at - ended.started_at,
        )
        return [("end", ended)]

    @staticmethod
    def _with_visitor(conversation: Conversation, visitor: Visitor) -> Conversation:
        visitors = tuple(visitor if v.person_id == visitor.person_id else v for v in conversation.visitors)
        return replace(conversation, visitors=visitors)

    # Playing -------------------------------------------------------------------

    def _play_one(self, reminder: _Reminder) -> None:
        with self._lock:
            current = self._conversation
            if current is None or current.id != reminder.conversation_id:
                log.info("not playing %s's reminder: their conversation is over", reminder.name)
                return
        if self._last_reminder_end is not None:
            wait = self.timing.reminder_pause - (self.clock() - self._last_reminder_end)
            if wait > 0:
                self.sleep(wait)
        try:
            played = bool(self.play(reminder.audio_file))
        except Exception:  # noqa: BLE001 - player.play never raises, but a swapped-in one might
            log.exception("playing %s's reminder failed", reminder.name)
            played = False
        self._last_reminder_end = self.clock()
        if played:
            log.info("reminder for %s played", reminder.name)
        else:
            log.warning("reminder for %s did not play; staying silent for this conversation", reminder.name)
        with self._lock:
            current = self._conversation
            if current is not None and current.id == reminder.conversation_id:
                visitor = current.visitor(reminder.person_id)
                if visitor is not None:
                    self._conversation = self._with_visitor(current, replace(visitor, reminder_played=played))

    # Hooks ---------------------------------------------------------------------

    def _fire(self, events: list[tuple[str, Conversation]]) -> None:
        for kind, conversation in events:
            hook = self.hooks.get(kind)
            if hook is None:
                continue
            try:
                hook(conversation)
            except Exception:  # noqa: BLE001
                log.exception("tracker on_%s hook failed", kind)


# Test entry -------------------------------------------------------------------


def _at(at: float | None) -> str:
    return datetime.fromtimestamp(at).strftime("%H:%M:%S") if at is not None else "?"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run listener + recognizer + tracker + player: one reminder per visitor per conversation."
    )
    parser.add_argument("--end-after", type=float, default=END_AFTER_SECONDS,
                        help=f"seconds without a visitor's voice before they count as away (default {END_AFTER_SECONDS})")
    parser.add_argument("--same-within", type=float, default=SAME_CONVERSATION_SECONDS,
                        help="seconds since last heard within which a return is the same conversation "
                             f"(default {SAME_CONVERSATION_SECONDS})")
    parser.add_argument("--pause", type=float, default=REMINDER_PAUSE_SECONDS,
                        help=f"seconds between two reminders (default {REMINDER_PAUSE_SECONDS})")
    parser.add_argument("--seconds", type=float, default=4.0, help="clip length from the mic, 3-5 (default 4)")
    parser.add_argument("--mic", help="input device name (default: the MacBook's built-in mic)")
    parser.add_argument("--device", help="part of the AirPod's output name (default: $ARGOS_AIRPOD_NAME or 'AirPods')")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help=f"default {DATA_DIR}")
    parser.add_argument("--dry-run", action="store_true", help="print which reminder would play instead of playing it")
    parser.add_argument("--quiet", action="store_true", help="hide the recognizer's per-clip scores")
    args = parser.parse_args()
    try:
        timing = Timing(args.end_after, args.same_within, args.pause)
    except ValueError as error:
        parser.error(str(error))

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.quiet:
        logging.getLogger("argos_station.recognizer").setLevel(logging.WARNING)

    from argos_station.config import load_env  # .env may set ARGOS_AIRPOD_NAME
    from argos_station.listener import Listener, MicNotFoundError
    from argos_station.recognizer import Recognizer

    load_env()

    if args.dry_run:
        def play(path: Path) -> bool:
            print(f"(dry run) would play {path.name}")
            return True
    else:
        from argos_station import player

        def play(path: Path) -> bool:
            return player.play(path, args.device)

    def show(label: str) -> Hook:
        def hook(c: Conversation) -> None:
            visitors = ", ".join(
                f"{v.name} (reminder {'played' if v.reminder_played else 'pending' if v.reminder_played is None else 'silent'})"
                for v in c.visitors
            )
            line = f">>> {label}: conversation {c.id[:8]}, started {_at(c.started_at)}, last heard {_at(c.last_heard_at)}"
            if c.ended_at is not None:
                line += f", ended {_at(c.ended_at)} ({c.end_reason})"
            print(f"{line}; visitors: {visitors or 'none yet'}", flush=True)
        return hook

    print("Loading the speaker model...")
    recognizer = Recognizer(args.data_dir)
    known = recognizer.voiceprints
    print(f"Voiceprints: {', '.join(vp.name + (' (patient)' if vp.is_patient else '') for vp in known) or 'none'}")
    tracker = Tracker(
        recognizer,
        timing=timing,
        on_start=show("STARTED"),
        on_away=show("AWAY"),
        on_return=show("RETURNED"),
        on_end=show("ENDED"),
        play=play,
        data_dir=args.data_dir,
    )
    listener = Listener(on_clip=tracker.on_clip, clip_seconds=args.seconds, mic_name=args.mic)
    tracker.start()
    try:
        listener.start()
    except MicNotFoundError:
        tracker.stop()
        raise SystemExit(1) from None
    print(
        f"Away after {timing.end_after:.0f} s without a visitor, same conversation within "
        f"{timing.same_conversation_within:.0f} s, {timing.reminder_pause:.1f} s between reminders. "
        "Speak; Ctrl+C to stop."
    )
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        listener.stop()
        tracker.stop()


if __name__ == "__main__":
    main()
