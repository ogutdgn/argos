"""Unit tests for the conversation rules in argos_station/tracker.py.

No mic, AirPod, model or Supabase: recognitions are made by hand, playing is a
fake, and a fake clock stands in for time, so the 5 and 30 minute rules run at
full length in milliseconds.

Run from station/:

    .venv/bin/python -m unittest discover -s tests -v
"""

import logging
import unittest
from pathlib import Path

from argos_station.recognizer import Kind, Recognition
from argos_station.sync import SyncedPerson, SyncedReminder
from argos_station.tracker import (
    END_AFTER_SECONDS,
    END_NEW_VISITOR,
    END_NOT_HEARD,
    END_STATION_STOPPED,
    REMINDER_PAUSE_SECONDS,
    SAME_CONVERSATION_SECONDS,
    Timing,
    Tracker,
)

MINUTE = 60.0
T0 = 1_800_000_000.0  # any fixed Unix time

# Fictional demo family (the Odyssey).
ODYSSEUS = "11111111-1111-1111-1111-111111111111"
PENELOPE = "22222222-2222-2222-2222-222222222222"
TELEMACHUS = "33333333-3333-3333-3333-333333333333"
LAERTES = "44444444-4444-4444-4444-444444444444"


def person(person_id: str, name: str, relationship: str | None, reminder: bool = True, patient: bool = False):
    return SyncedPerson(
        id=person_id,
        name=name,
        relationship=relationship,
        is_patient=patient,
        voice_sample_file=None,
        reminder=SyncedReminder(
            id=f"r-{name}", text=f"{name}, your {relationship}.", created_at="", audio_file=Path(f"/fake/{name}.mp3")
        )
        if reminder
        else None,
    )


PEOPLE = [
    person(ODYSSEUS, "Odysseus", "son"),
    person(PENELOPE, "Penelope", "daughter-in-law"),
    person(TELEMACHUS, "Telemachus", "grandson"),
    person(LAERTES, "Laertes", None, reminder=False, patient=True),
]


def visitor(person_id: str) -> Recognition:
    name = next(p.name for p in PEOPLE if p.id == person_id)
    return Recognition(Kind.VISITOR, "match", person_id=person_id, name=name, score=0.7)


PATIENT = Recognition(Kind.PATIENT, "patient")
UNKNOWN = Recognition(Kind.UNKNOWN, "below threshold")


def setUpModule() -> None:
    logging.disable(logging.CRITICAL)  # the tracker logs every decision; not needed here


def tearDownModule() -> None:
    logging.disable(logging.NOTSET)


class Clock:
    def __init__(self) -> None:
        self.now = T0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TrackerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.people = list(PEOPLE)
        self.played: list[tuple[str, float]] = []  # (file name, when it started)
        self.events: list[tuple[str, object]] = []
        self.play_result = True
        self.tracker = self.make()

    def make(self, timing: Timing = Timing()) -> Tracker:
        def hook(kind: str):
            return lambda conversation: self.events.append((kind, conversation))

        def play(path: Path) -> bool:
            self.played.append((path.stem, self.clock.now))
            self.clock.advance(4.0)  # a reminder takes about 4 s
            return self.play_result

        return Tracker(
            timing=timing,
            on_start=hook("start"),
            on_away=hook("away"),
            on_return=hook("return"),
            on_end=hook("end"),
            play=play,
            people=lambda: self.people,
            clock=self.clock,
            sleep=self.clock.sleep,
        )

    def hear(self, result: Recognition) -> None:
        self.tracker.heard(result)
        self.tracker.play_pending()

    def wait(self, seconds: float, step: float = 1.0) -> None:
        """Let time pass, checking the timers every ``step`` like the timer thread."""
        end = self.clock.now + seconds
        while self.clock.now < end:
            self.clock.advance(min(step, end - self.clock.now))
            self.tracker.tick()

    def kinds(self) -> list[str]:
        return [kind for kind, _ in self.events]

    # Flow B ---------------------------------------------------------------------

    def test_known_visitor_starts_a_conversation_and_hears_the_reminder_once(self):
        self.hear(visitor(ODYSSEUS))
        self.assertEqual(self.kinds(), ["start"])
        self.assertEqual([name for name, _ in self.played], ["Odysseus"])

        for _ in range(5):  # keeps talking: more clips, same conversation
            self.wait(MINUTE)
            self.hear(visitor(ODYSSEUS))
        self.assertEqual(len(self.played), 1)
        self.assertEqual(self.kinds(), ["start"])
        conversation = self.tracker.conversation
        self.assertEqual(conversation.person_ids, (ODYSSEUS,))
        self.assertTrue(conversation.visitor(ODYSSEUS).reminder_played)

    def test_patient_and_unknown_never_start_anything_or_play(self):
        for result in (PATIENT, UNKNOWN, PATIENT, UNKNOWN):
            self.hear(result)
        self.wait(SAME_CONVERSATION_SECONDS + MINUTE, step=MINUTE)
        self.assertIsNone(self.tracker.conversation)
        self.assertEqual(self.played, [])
        self.assertEqual(self.events, [])

    def test_patient_and_unknown_do_not_keep_a_conversation_going(self):
        self.hear(visitor(ODYSSEUS))
        for _ in range(4):  # only the patient and a stranger talk for 5 minutes
            self.wait(1.25 * MINUTE)
            self.hear(PATIENT)
            self.hear(UNKNOWN)
        self.assertEqual(self.kinds(), ["start", "away"])

    # Flow C: 5 minutes -----------------------------------------------------------

    def test_away_after_five_minutes_without_the_visitor(self):
        self.hear(visitor(ODYSSEUS))
        last_heard = self.clock.now - 4.0  # heard, then the 4 s reminder played
        self.wait(END_AFTER_SECONDS - 4.0 - 1.0)
        self.assertEqual(self.kinds(), ["start"])
        self.wait(1.0)
        self.assertEqual(self.kinds(), ["start", "away"])
        away = self.events[-1][1]
        self.assertTrue(away.away)
        self.assertEqual(away.last_heard_at, last_heard)
        self.assertIsNone(away.ended_at)

    # Edge case: back within 30 minutes --------------------------------------------

    def test_return_within_thirty_minutes_is_the_same_conversation(self):
        self.hear(visitor(ODYSSEUS))
        first_id = self.tracker.conversation.id
        self.wait(10 * MINUTE)  # restroom
        self.hear(visitor(ODYSSEUS))
        self.assertEqual(self.kinds(), ["start", "away", "return"])
        self.assertEqual(self.tracker.conversation.id, first_id)
        self.assertFalse(self.tracker.conversation.away)
        self.assertEqual(len(self.played), 1)  # no new reminder

    def test_the_end_waits_until_they_really_leave(self):
        self.hear(visitor(ODYSSEUS))
        self.wait(10 * MINUTE)
        self.hear(visitor(ODYSSEUS))  # back after 10 min
        back_at = self.clock.now
        self.wait(SAME_CONVERSATION_SECONDS - 1.0, step=MINUTE / 2)
        self.assertEqual(self.kinds(), ["start", "away", "return", "away"])  # not ended yet
        self.wait(1.0)
        self.assertEqual(self.kinds(), ["start", "away", "return", "away", "end"])
        ended = self.events[-1][1]
        self.assertEqual(ended.end_reason, END_NOT_HEARD)
        self.assertEqual(ended.ended_at, back_at)  # ends when they were last heard
        self.assertEqual(ended.started_at, T0)
        self.assertIsNone(self.tracker.conversation)

    def test_back_after_thirty_minutes_is_a_new_conversation_with_a_new_reminder(self):
        self.hear(visitor(ODYSSEUS))
        first_id = self.tracker.conversation.id
        self.wait(SAME_CONVERSATION_SECONDS + MINUTE, step=MINUTE)
        self.hear(visitor(ODYSSEUS))
        self.assertEqual(self.kinds(), ["start", "away", "end", "start"])
        self.assertNotEqual(self.tracker.conversation.id, first_id)
        self.assertEqual([name for name, _ in self.played], ["Odysseus", "Odysseus"])

    def test_late_clip_without_a_timer_tick_still_ends_the_old_conversation_first(self):
        self.hear(visitor(ODYSSEUS))
        self.clock.advance(SAME_CONVERSATION_SECONDS + MINUTE)  # no tick in between
        self.hear(visitor(ODYSSEUS))
        self.assertEqual(self.kinds(), ["start", "end", "start"])

    # Edge case: two visitors at once ------------------------------------------------

    def test_two_visitors_get_one_reminder_each_with_a_pause(self):
        self.tracker.heard(visitor(ODYSSEUS))
        self.tracker.heard(visitor(PENELOPE))
        self.tracker.play_pending()
        self.assertEqual([name for name, _ in self.played], ["Odysseus", "Penelope"])
        first_start, second_start = self.played[0][1], self.played[1][1]
        self.assertAlmostEqual(second_start - (first_start + 4.0), REMINDER_PAUSE_SECONDS)
        self.assertEqual(self.clock.slept, [REMINDER_PAUSE_SECONDS])

        for _ in range(3):
            self.wait(MINUTE)
            self.hear(visitor(PENELOPE))
            self.hear(visitor(ODYSSEUS))
        self.assertEqual(len(self.played), 2)
        self.assertEqual(self.kinds(), ["start"])
        self.assertEqual(self.tracker.conversation.person_ids, (ODYSSEUS, PENELOPE))

    def test_a_visitor_who_keeps_talking_keeps_the_conversation_open_for_both(self):
        self.hear(visitor(ODYSSEUS))
        self.hear(visitor(PENELOPE))
        for _ in range(10):  # Odysseus steps out; Penelope keeps talking
            self.wait(2 * MINUTE)
            self.hear(visitor(PENELOPE))
        self.assertEqual(self.kinds(), ["start"])
        self.wait(2 * MINUTE)
        self.hear(visitor(ODYSSEUS))  # back after 22 min, Penelope never left
        self.assertEqual(self.kinds(), ["start"])
        self.assertEqual(len(self.played), 2)

    def test_someone_new_while_the_others_are_away_starts_a_new_conversation(self):
        self.hear(visitor(ODYSSEUS))
        odysseus_heard = self.clock.now - 4.0
        self.wait(10 * MINUTE)
        self.hear(visitor(TELEMACHUS))
        self.assertEqual(self.kinds(), ["start", "away", "end", "start"])
        ended = self.events[2][1]
        self.assertEqual(ended.end_reason, END_NEW_VISITOR)
        self.assertEqual(ended.ended_at, odysseus_heard)
        self.assertEqual(ended.person_ids, (ODYSSEUS,))
        self.assertEqual(self.tracker.conversation.person_ids, (TELEMACHUS,))
        self.assertEqual([name for name, _ in self.played], ["Odysseus", "Telemachus"])

    # Silence over mistakes ---------------------------------------------------------

    def test_no_reminder_yet_plays_nothing_but_the_conversation_is_tracked(self):
        self.people = [person(ODYSSEUS, "Odysseus", "son", reminder=False)]
        self.hear(visitor(ODYSSEUS))
        self.assertEqual(self.played, [])
        self.assertEqual(self.kinds(), ["start"])
        self.assertIs(self.tracker.conversation.visitor(ODYSSEUS).reminder_played, False)

        self.people = list(PEOPLE)  # the reminder arrives mid-conversation: still not played
        self.wait(MINUTE)
        self.hear(visitor(ODYSSEUS))
        self.assertEqual(self.played, [])

    def test_a_failed_reminder_is_not_tried_again_in_the_same_conversation(self):
        self.play_result = False  # e.g. no AirPod
        self.hear(visitor(ODYSSEUS))
        self.play_result = True
        self.wait(MINUTE)
        self.hear(visitor(ODYSSEUS))
        self.assertEqual(len(self.played), 1)
        self.assertIs(self.tracker.conversation.visitor(ODYSSEUS).reminder_played, False)

    def test_unknown_person_in_synced_people_plays_nothing(self):
        self.people = []
        self.hear(visitor(ODYSSEUS))
        self.assertEqual(self.played, [])
        self.assertEqual(self.kinds(), ["start"])

    def test_errors_play_nothing_and_never_raise(self):
        def broken_people():
            raise OSError("index unreadable")

        self.tracker.people = broken_people
        self.hear(visitor(ODYSSEUS))
        self.assertEqual(self.played, [])

        def broken_play(path):
            raise RuntimeError("audio system gone")

        self.tracker = self.make()
        self.tracker.play = broken_play
        self.hear(visitor(ODYSSEUS))  # must not raise
        self.assertIs(self.tracker.conversation.visitor(ODYSSEUS).reminder_played, False)

    def test_a_failing_hook_does_not_stop_the_tracker(self):
        def broken(conversation):
            raise RuntimeError("recorder crashed")

        self.tracker.hooks["start"] = broken
        self.hear(visitor(ODYSSEUS))
        self.assertEqual(len(self.played), 1)
        self.wait(END_AFTER_SECONDS)
        self.assertEqual(self.kinds(), ["away"])

    def test_a_queued_reminder_is_dropped_if_its_conversation_ended(self):
        self.tracker.heard(visitor(ODYSSEUS))
        self.tracker.end_now()
        self.tracker.play_pending()
        self.assertEqual(self.played, [])

    # Timing and stopping ------------------------------------------------------------

    def test_shortened_timing(self):
        self.tracker = self.make(Timing(end_after=20, same_conversation_within=60, reminder_pause=0.5))
        self.hear(visitor(ODYSSEUS))
        self.wait(20)
        self.assertEqual(self.kinds(), ["start", "away"])
        self.wait(40)
        self.assertEqual(self.kinds(), ["start", "away", "end"])

    def test_timing_is_checked(self):
        with self.assertRaises(ValueError):
            Timing(end_after=0)
        with self.assertRaises(ValueError):
            Timing(end_after=60, same_conversation_within=30)
        with self.assertRaises(ValueError):
            Timing(reminder_pause=-1)
        self.assertEqual(Timing(), Timing(5 * MINUTE, 30 * MINUTE, REMINDER_PAUSE_SECONDS))

    def test_end_now_ends_an_open_conversation(self):
        self.hear(visitor(ODYSSEUS))
        self.tracker.end_now()
        self.assertEqual(self.kinds(), ["start", "end"])
        self.assertEqual(self.events[-1][1].end_reason, END_STATION_STOPPED)
        self.tracker.end_now()  # nothing open: nothing happens
        self.assertEqual(self.kinds(), ["start", "end"])

    def test_threads_recognize_clips_and_play(self):
        import threading
        import time

        played = threading.Event()

        class FakeRecognizer:
            def recognize(self, clip):
                return visitor(ODYSSEUS)

        events = []
        tracker = Tracker(
            FakeRecognizer(),
            on_start=lambda c: events.append("start"),
            on_end=lambda c: events.append(c.end_reason),
            play=lambda path: played.set() or True,
            people=lambda: self.people,
            tick_seconds=0.01,
        )
        tracker.on_clip("ignored before start")
        tracker.start()
        tracker.on_clip("a clip")
        self.assertTrue(played.wait(2))
        tracker.stop()
        time.sleep(0.01)
        self.assertEqual(events, ["start", END_STATION_STOPPED])


if __name__ == "__main__":
    unittest.main()
