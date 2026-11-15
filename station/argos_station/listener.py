"""Listens through the MacBook mic and detects speech.

The listener opens the MacBook's built-in mic (never the AirPod mic), runs every
32 ms of audio through Silero VAD, and reports speech through callbacks.

Interface for the other station modules::

    from argos_station.listener import Listener

    listener = Listener(
        on_speech_start=lambda event: ...,  # SpeechStarted: someone started speaking
        on_clip=lambda clip: ...,           # SpeechClip: the first N seconds of that speech
        on_speech_stop=lambda event: ...,   # SpeechStopped: they stopped speaking
        on_audio=lambda frame: ...,         # optional: every raw 32 ms frame, for recording
        clip_seconds=4.0,                   # N, between 3 and 5
    )
    listener.start()   # raises MicNotFoundError if the MacBook mic is missing
    ...
    listener.stop()    # or use ``with Listener(...) as listener:``

Events, per stretch of speech, always in this order:

1. ``SpeechStarted(at)`` once speech has lasted ``MIN_SPEECH_MS``. ``at`` is when
   the speech began (Unix time), not when it was confirmed.
2. ``SpeechClip(audio, sample_rate, started_at)``, at most once: the first
   ``clip_seconds`` of the speech, starting ``PRE_ROLL_MS`` before it so the first
   syllable is not cut. Sent as soon as that much audio exists, while the person is
   still talking. If they stop sooner, the clip is whatever they said, but only
   if they spoke for at least ``MIN_CLIP_SECONDS``; shorter speech gets no clip
   (too little to recognize safely: silence over mistakes).
3. ``SpeechStopped(at, duration)`` after ``MIN_SILENCE_MS`` of silence. ``at`` is
   when the silence began. Also sent by ``stop()`` if someone is mid-speech.

Clip audio is 16 kHz mono float32 in [-1, 1] (1-D ``numpy`` array), the format the
SpeechBrain voice model takes directly (see ``scripts/voice_test.py``).

Callbacks run one at a time on the listener's own thread, never on the audio
thread. Mic audio keeps buffering while a callback runs, so nothing is lost, but
events after it are delayed: hand slow work (like recognition) to your own thread
if latency matters. An exception in a callback is logged and the listener keeps
running.

The Silero model ships inside the ``silero-vad`` package (in ``.venv``), so
nothing is downloaded and nothing is written to disk. Audio stays in memory.

Try it (prints the events; ``--help`` for options)::

    python -m argos_station.listener
"""

from __future__ import annotations

import argparse
import logging
import queue
import tempfile
import threading
import time
import wave
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000  # What the SpeechBrain voice model expects (S0.2).
FRAME_SAMPLES = 512  # Silero VAD takes exactly 512 samples (32 ms) per call at 16 kHz.

START_THRESHOLD = 0.5  # Speech probability that counts as speech.
STOP_THRESHOLD = 0.35  # Below this counts as silence. The gap stops flicker around 0.5.
MIN_SPEECH_MS = 250  # Speech this long in a row before "started" (ignores clicks and coughs).
MIN_SILENCE_MS = 800  # Silence this long before "stopped" (short pauses don't split a greeting).
PRE_ROLL_MS = 200  # Audio kept from just before the speech, so the first syllable is not cut.

DEFAULT_CLIP_SECONDS = 4.0
MIN_CLIP_SECONDS = 3.0  # Flow B: 3-5 s of speech before recognition.
MAX_CLIP_SECONDS = 5.0

# The MacBook's own mic, by name. Recent macOS says "MacBook Pro Microphone" or
# "MacBook Air Microphone"; older macOS says "Built-in Microphone".
BUILT_IN_MIC_NAMES = ("macbook", "built-in")
# Never the AirPod mic: the visitor is not speaking into it, and opening it drops the
# AirPod into low-quality call mode, which would spoil the reminder in the patient's ear.
EXCLUDED_MIC_NAMES = ("airpods",)


@dataclass(frozen=True)
class SpeechStarted:
    at: float  # Unix time when the speech began.


@dataclass(frozen=True)
class SpeechClip:
    started_at: float  # Unix time of the SpeechStarted this clip belongs to.
    audio: np.ndarray = field(repr=False)  # 1-D float32, mono, in [-1, 1].
    sample_rate: int = SAMPLE_RATE

    @property
    def seconds(self) -> float:
        return len(self.audio) / self.sample_rate


@dataclass(frozen=True)
class SpeechStopped:
    at: float  # Unix time when the silence began.
    duration: float  # Seconds from the start of the speech to the start of the silence.


SpeechEvent = SpeechStarted | SpeechClip | SpeechStopped


class MicNotFoundError(RuntimeError):
    """The MacBook's built-in mic (or the named mic) is not available."""


def frames_for(ms: float) -> int:
    """How many 32 ms frames cover ``ms`` milliseconds (at least one)."""
    return max(1, round(ms / 1000 * SAMPLE_RATE / FRAME_SAMPLES))


def load_vad() -> Callable[[np.ndarray], float]:
    """Load Silero VAD. Returns a function: one 512-sample frame -> speech probability."""
    import torch
    from silero_vad import load_silero_vad

    # ONNX: faster here, and torch.jit loading is deprecated on Python 3.14+.
    model = load_silero_vad(onnx=True)

    def speech_probability(frame: np.ndarray) -> float:
        with torch.no_grad():
            return float(model(torch.from_numpy(frame), SAMPLE_RATE).item())

    return speech_probability


class SpeechDetector:
    """Turns 512-sample frames into speech events. No mic involved, so it runs on any audio.

    ``vad`` maps one frame to a speech probability; it defaults to Silero VAD. The
    model keeps state between frames, so feed one continuous stream per detector.
    """

    def __init__(
        self,
        clip_seconds: float = DEFAULT_CLIP_SECONDS,
        start_time: float = 0.0,
        vad: Callable[[np.ndarray], float] | None = None,
    ) -> None:
        if not MIN_CLIP_SECONDS <= clip_seconds <= MAX_CLIP_SECONDS:
            raise ValueError(
                f"clip_seconds must be {MIN_CLIP_SECONDS}-{MAX_CLIP_SECONDS}, got {clip_seconds}"
            )
        self.vad = vad or load_vad()
        self.clip_samples = round(clip_seconds * SAMPLE_RATE)
        self.min_clip_samples = round(MIN_CLIP_SECONDS * SAMPLE_RATE)
        self.start_time = start_time
        self.samples_seen = 0

        self.speaking = False
        self.speech_run = 0  # Frames in a row at or above START_THRESHOLD, while quiet.
        self.silence_run = 0  # Frames since the silence began, while speaking.
        # Enough recent frames to reach back to the speech onset plus the pre-roll.
        self.recent: deque[np.ndarray] = deque(maxlen=frames_for(MIN_SPEECH_MS) + frames_for(PRE_ROLL_MS))
        self.clip: list[np.ndarray] = []
        self.clip_sent = False
        self.started_sample = 0

    def time_at(self, sample: int) -> float:
        return self.start_time + sample / SAMPLE_RATE

    def process(self, frame: np.ndarray) -> list[SpeechEvent]:
        """Feed one frame of FRAME_SAMPLES mono float32 samples. Returns the events it caused."""
        frame = np.ascontiguousarray(frame, dtype=np.float32).reshape(-1)
        if len(frame) != FRAME_SAMPLES:
            raise ValueError(f"expected {FRAME_SAMPLES} samples, got {len(frame)}")

        prob = self.vad(frame)
        frame_start = self.samples_seen
        self.samples_seen += FRAME_SAMPLES
        self.recent.append(frame)

        if not self.speaking:
            return self._while_quiet(prob, frame_start)
        return self._while_speaking(prob, frame, frame_start)

    def flush(self) -> list[SpeechEvent]:
        """End any speech in progress, as if silence began now. Call when the audio ends."""
        if not self.speaking:
            return []
        return self._end_speech(silence_start=self.samples_seen, silence_frames=0)

    def _while_quiet(self, prob: float, frame_start: int) -> list[SpeechEvent]:
        self.speech_run = self.speech_run + 1 if prob >= START_THRESHOLD else 0
        if self.speech_run < frames_for(MIN_SPEECH_MS):
            return []

        self.speaking = True
        self.started_sample = frame_start - (self.speech_run - 1) * FRAME_SAMPLES  # First frame of the run.
        self.speech_run = 0
        self.silence_run = 0
        self.clip = list(self.recent)  # The speech so far plus the pre-roll before it.
        self.clip_sent = False
        return [SpeechStarted(at=self.time_at(self.started_sample)), *self._clip_if_full()]

    def _while_speaking(self, prob: float, frame: np.ndarray, frame_start: int) -> list[SpeechEvent]:
        # Silence begins below STOP_THRESHOLD and lasts until speech is clear again.
        if prob >= START_THRESHOLD:
            self.silence_run = 0
        elif prob < STOP_THRESHOLD or self.silence_run:
            self.silence_run += 1
        if not self.clip_sent:
            self.clip.append(frame)

        if self.silence_run < frames_for(MIN_SILENCE_MS):
            return self._clip_if_full()
        silence_start = frame_start - (self.silence_run - 1) * FRAME_SAMPLES
        return self._end_speech(silence_start, self.silence_run)

    def _end_speech(self, silence_start: int, silence_frames: int) -> list[SpeechEvent]:
        events: list[SpeechEvent] = []
        if not self.clip_sent and silence_start - self.started_sample >= self.min_clip_samples:
            # Speech ended before the clip filled but lasted long enough to recognize
            # (the pre-roll doesn't count): send what was said, minus the trailing silence.
            events.append(self._make_clip(self.clip[: len(self.clip) - silence_frames]))
        started_at = self.time_at(self.started_sample)
        stopped_at = self.time_at(silence_start)
        events.append(SpeechStopped(at=stopped_at, duration=stopped_at - started_at))

        self.speaking = False
        self.silence_run = 0
        self.clip = []
        self.recent.clear()
        return events

    def _clip_if_full(self) -> list[SpeechEvent]:
        # Frames of a silence that may be the end of the speech don't fill the clip;
        # if the person speaks again, they count as a pause inside the speech.
        spoken_frames = len(self.clip) - self.silence_run
        if self.clip_sent or spoken_frames * FRAME_SAMPLES < self.clip_samples:
            return []
        return [self._make_clip(self.clip)]

    def _make_clip(self, frames: list[np.ndarray]) -> SpeechClip:
        audio = np.concatenate(frames)[: self.clip_samples]
        self.clip_sent = True
        self.clip = []
        return SpeechClip(started_at=self.time_at(self.started_sample), audio=audio, sample_rate=SAMPLE_RATE)


def input_devices() -> list[tuple[int, str]]:
    """All audio inputs as (device index, name)."""
    import sounddevice as sd

    return [
        (index, device["name"])
        for index, device in enumerate(sd.query_devices())
        if device["max_input_channels"] > 0
    ]


def find_mic(name: str | None = None) -> tuple[int, str]:
    """Return (device index, name) of the MacBook's built-in mic, or of the input called ``name``.

    Picks the mic by name, never the system default, because the AirPod mic can become
    the default when the AirPod connects. Never returns an AirPod mic. Raises
    MicNotFoundError (after logging it) instead of falling back to another mic.
    """
    inputs = input_devices()
    allowed = [(i, n) for i, n in inputs if not any(x in n.lower() for x in EXCLUDED_MIC_NAMES)]

    if name:
        matches = [(i, n) for i, n in allowed if n == name] or [
            (i, n) for i, n in allowed if name.lower() in n.lower()
        ]
    else:
        matches = [
            (i, n)
            for i, n in allowed
            if "microphone" in n.lower() and any(x in n.lower() for x in BUILT_IN_MIC_NAMES)
        ]
    if not matches:
        wanted = f'the mic "{name}"' if name else "the MacBook's built-in mic"
        found = ", ".join(f'"{n}"' for _, n in inputs) or "none"
        message = f"Could not find {wanted} (AirPod mics are never used). Inputs: {found}"
        log.error(message)
        raise MicNotFoundError(message)
    return matches[0]


class Listener:
    """Streams the MacBook mic through the speech detector and calls back on speech events."""

    def __init__(
        self,
        on_speech_start: Callable[[SpeechStarted], None] | None = None,
        on_clip: Callable[[SpeechClip], None] | None = None,
        on_speech_stop: Callable[[SpeechStopped], None] | None = None,
        on_audio: Callable[[np.ndarray], None] | None = None,
        clip_seconds: float = DEFAULT_CLIP_SECONDS,
        mic_name: str | None = None,
    ) -> None:
        if not MIN_CLIP_SECONDS <= clip_seconds <= MAX_CLIP_SECONDS:
            raise ValueError(
                f"clip_seconds must be {MIN_CLIP_SECONDS}-{MAX_CLIP_SECONDS}, got {clip_seconds}"
            )
        self.on_speech_start = on_speech_start
        self.on_clip = on_clip
        self.on_speech_stop = on_speech_stop
        self.on_audio = on_audio
        self.clip_seconds = clip_seconds
        self.mic_name = mic_name
        self.device: int | None = None
        self.device_name: str | None = None

        self._frames: queue.Queue[np.ndarray] = queue.Queue()
        self._stream = None
        self._thread: threading.Thread | None = None
        self._running = threading.Event()

    def start(self) -> None:
        """Open the MacBook mic and start listening. Raises MicNotFoundError if it is missing."""
        if self._running.is_set():
            return
        import sounddevice as sd

        self.device, self.device_name = find_mic(self.mic_name)
        detector = SpeechDetector(self.clip_seconds)  # Load the model before the mic opens.
        self._frames = queue.Queue()
        self._stream = sd.InputStream(
            device=self.device,
            channels=1,
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SAMPLES,
            dtype="float32",
            callback=self._on_mic_audio,
        )
        detector.start_time = time.time()
        self._running.set()
        self._stream.start()
        self._thread = threading.Thread(target=self._run, args=(detector,), name="listener", daemon=True)
        self._thread.start()
        log.info('Listening on "%s" at %d Hz', self.device_name, SAMPLE_RATE)

    def stop(self) -> None:
        """Close the mic. Sends SpeechStopped (and a clip, if one is due) if someone is mid-speech."""
        if not self._running.is_set():
            return
        self._running.clear()
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def __enter__(self) -> Listener:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def _on_mic_audio(self, indata: np.ndarray, frame_count: int, time_info, status) -> None:
        # Audio thread: copy the frame and get out. All work happens in _run.
        if status:
            log.warning("mic: %s", status)
        self._frames.put(indata[:, 0].copy())

    def _run(self, detector: SpeechDetector) -> None:
        last_audio = time.monotonic()
        warned = False
        while self._running.is_set() or not self._frames.empty():
            try:
                frame = self._frames.get(timeout=0.25)
            except queue.Empty:
                if self._running.is_set() and not warned and time.monotonic() - last_audio > 2:
                    log.warning('No audio from "%s" for 2 s', self.device_name)
                    warned = True
                continue
            last_audio = time.monotonic()
            warned = False
            self._call(self.on_audio, frame)
            try:
                events = detector.process(frame)
            except Exception:
                log.exception("Speech detection failed on a frame; skipping it")
                continue
            for event in events:
                self._dispatch(event)
        for event in detector.flush():
            self._dispatch(event)

    def _dispatch(self, event: SpeechEvent) -> None:
        if isinstance(event, SpeechStarted):
            self._call(self.on_speech_start, event)
        elif isinstance(event, SpeechClip):
            self._call(self.on_clip, event)
        else:
            self._call(self.on_speech_stop, event)

    @staticmethod
    def _call(callback: Callable | None, value) -> None:
        if callback is None:
            return
        try:
            callback(value)
        except Exception:
            log.exception("Listener callback %s failed", getattr(callback, "__name__", callback))


def _clock(at: float) -> str:
    return datetime.fromtimestamp(at).strftime("%H:%M:%S.%f")[:-3]


def _save_wav(path: Path, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm.tobytes())


def main() -> None:
    parser = argparse.ArgumentParser(description="Print speech events from the MacBook mic.")
    parser.add_argument("--seconds", type=float, default=DEFAULT_CLIP_SECONDS, help="clip length, 3-5 (default 4)")
    parser.add_argument("--mic", help="input device name (default: the MacBook's built-in mic)")
    parser.add_argument("--list", action="store_true", help="list the inputs and which one would be used")
    parser.add_argument("--save", action="store_true", help="save each clip as .wav in a temp folder")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.list:
        for index, name in input_devices():
            print(f"{index:>3}  {name}")
        try:
            index, name = find_mic(args.mic)
            print(f'Would use: {index} "{name}"')
        except MicNotFoundError:
            pass  # Already logged.
        return

    save_dir = Path(tempfile.mkdtemp(prefix="argos-listener-")) if args.save else None
    clips = 0

    def started(event: SpeechStarted) -> None:
        print(f"{_clock(event.at)}  speech started")

    def clip_ready(clip: SpeechClip) -> None:
        nonlocal clips
        clips += 1
        level = float(np.sqrt(np.mean(clip.audio**2)))
        line = (
            f"{_clock(time.time())}  clip ready: {clip.seconds:.2f} s, {len(clip.audio)} samples, "
            f"{clip.sample_rate} Hz {clip.audio.dtype} mono, level {level:.3f}"
        )
        if save_dir is not None:
            path = save_dir / f"clip_{clips}.wav"
            _save_wav(path, clip.audio)
            line += f", saved {path}"
        print(line)

    def stopped(event: SpeechStopped) -> None:
        print(f"{_clock(event.at)}  speech stopped after {event.duration:.1f} s")

    listener = Listener(
        on_speech_start=started,
        on_clip=clip_ready,
        on_speech_stop=stopped,
        clip_seconds=args.seconds,
        mic_name=args.mic,
    )
    try:
        listener.start()
    except MicNotFoundError:
        raise SystemExit(1) from None
    print(f"Clip length {args.seconds} s. Speak; Ctrl+C to stop.")
    if save_dir is not None:
        print(f"Clips go to {save_dir} (outside the repo; delete it when done).")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        listener.stop()


if __name__ == "__main__":
    main()
