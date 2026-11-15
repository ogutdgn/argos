"""Plays a reminder audio file into the AirPod only.

Interface for the tracker (S2.1):

    from argos_station import player

    ok = player.play(path)  # blocks until the clip ends; True only if it played to the end

Rules it keeps:

- **AirPod only.** The output device is picked by name on every call, never the
  system default. The name is a case-insensitive part of the device name, from
  `ARGOS_AIRPOD_NAME` (default "AirPods"), or the `device_name` argument. A device
  whose name looks built-in (MacBook speakers) is never used, even if it matches.
  No AirPod found means nothing plays: there is no fallback to the speakers.
- **Silence over mistakes.** Any problem (no AirPod, missing or unreadable file,
  empty audio, the AirPod dropping out mid-play) is logged, never raised, and
  `play()` returns False. The whole file is decoded before anything plays, so a
  broken file plays nothing rather than half a reminder.
- **One at a time.** Calls take turns behind a lock, so two reminders never
  overlap. For two visitors the tracker calls `play(a)`, waits a short pause,
  then calls `play(b)`.

Audio: `.mp3` (the `reminder-audio` bucket) and `.wav` are decoded by soundfile.
Its wheel bundles libsndfile with MP3 support, so no ffmpeg is needed.

Limitation: PortAudio reads the list of audio devices once, when the process
first uses sounddevice. An AirPod connected after that is not seen until the
station restarts, so connect the AirPod before starting it. (Re-reading the list
would mean restarting PortAudio, which would break the listener's mic stream in
the same process.)

Test from station/ (a fresh process each time):

    .venv/bin/python -m argos_station.player --list
    .venv/bin/python -m argos_station.player --sample
    .venv/bin/python -m argos_station.player path/to/reminder.mp3 [--device NAME] [--repeat N]
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

log = logging.getLogger(__name__)

DEFAULT_DEVICE_NAME = "AirPods"
DEVICE_NAME_ENV = "ARGOS_AIRPOD_NAME"

# Never play into a device whose name contains one of these, whatever the match says.
BUILT_IN_MARKERS = ("macbook", "built-in")

# Extra wait on top of the clip length before playback counts as stuck (Bluetooth starts slowly).
STUCK_MARGIN_SECONDS = 3.0

# Fictional demo line (the Odyssey family), used only by --sample.
SAMPLE_TEXT = "Odysseus, your son. Ask him about the olive trees in the orchard."

_play_lock = threading.Lock()


def device_name_wanted(device_name: str | None = None) -> str:
    """The name to look for: the argument, else ARGOS_AIRPOD_NAME, else "AirPods"."""
    if device_name is None:
        device_name = os.environ.get(DEVICE_NAME_ENV) or DEFAULT_DEVICE_NAME
    return device_name.strip()


def _is_built_in(name: str) -> bool:
    lowered = name.casefold()
    return any(marker in lowered for marker in BUILT_IN_MARKERS)


def output_devices() -> list[dict]:
    """All devices that can play sound, as sounddevice reports them (with "index")."""
    return [device for device in sd.query_devices() if device["max_output_channels"] > 0]


def find_airpod(device_name: str | None = None) -> dict | None:
    """Return the first non-built-in output device whose name contains the wanted name, or None."""
    wanted = device_name_wanted(device_name)
    if not wanted:
        log.error("Empty device name to match; refusing to pick an output device.")
        return None
    matches = [d for d in output_devices() if wanted.casefold() in d["name"].casefold()]
    safe = [d for d in matches if not _is_built_in(d["name"])]
    for device in matches:
        if device not in safe:
            log.warning("Skipping %r: it looks like a built-in device.", device["name"])
    if len(safe) > 1:
        log.info("Several devices match %r; using %r.", wanted, safe[0]["name"])
    return safe[0] if safe else None


def _load(path: Path) -> tuple[np.ndarray, int]:
    """Decode the whole file into float32 frames x channels. Raises on any problem."""
    if not path.is_file():
        raise FileNotFoundError(f"no such file: {path}")
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    if audio.shape[0] == 0:
        raise ValueError("the file has no audio")
    if not np.isfinite(audio).all():
        raise ValueError("the audio has invalid samples")
    return audio, int(sample_rate)


def _fit_channels(audio: np.ndarray, channels: int) -> np.ndarray:
    """A mono reminder goes to both ears, so it is heard whichever AirPod is in."""
    if audio.shape[1] >= channels:
        return np.ascontiguousarray(audio[:, :channels])
    return np.ascontiguousarray(np.repeat(audio.mean(axis=1, keepdims=True), channels, axis=1))


def _resample(audio: np.ndarray, rate_in: int, rate_out: int) -> np.ndarray:
    """Linear resampling; good enough for one spoken sentence."""
    frames_out = max(1, round(audio.shape[0] * rate_out / rate_in))
    t_in = np.arange(audio.shape[0]) / rate_in
    t_out = np.arange(frames_out) / rate_out
    columns = [np.interp(t_out, t_in, audio[:, c]) for c in range(audio.shape[1])]
    return np.stack(columns, axis=1).astype(np.float32)


def _stream_rate(device: dict, channels: int, sample_rate: int) -> int:
    """Use the file's rate if the device takes it, else the device's own rate."""
    try:
        sd.check_output_settings(device=device["index"], channels=channels, dtype="float32", samplerate=sample_rate)
        return sample_rate
    except Exception:  # noqa: BLE001 - any refusal means: use the device's rate
        return int(device["default_samplerate"])


def _play_frames(device: dict, audio: np.ndarray, sample_rate: int) -> bool:
    """Play frames on one device; False if it fails or never finishes."""
    finished = threading.Event()
    position = 0

    def callback(outdata, frames, _time, _status):
        nonlocal position
        chunk = audio[position:position + frames]
        outdata[:len(chunk)] = chunk
        position += len(chunk)
        if len(chunk) < frames:
            outdata[len(chunk):] = 0
            raise sd.CallbackStop  # plays what is buffered, then finishes

    limit = audio.shape[0] / sample_rate + STUCK_MARGIN_SECONDS
    stream = sd.OutputStream(
        device=device["index"],
        samplerate=sample_rate,
        channels=audio.shape[1],
        dtype="float32",
        latency="high",
        callback=callback,
        finished_callback=finished.set,
    )
    with stream:
        if not finished.wait(limit):
            stream.abort()
            log.error("Playback into %r did not finish in %.1f s; the AirPod may have dropped out.", device["name"], limit)
            return False
    if position < audio.shape[0]:
        log.error("Playback into %r stopped early (%d of %d frames).", device["name"], position, audio.shape[0])
        return False
    return True


def play(path: str | Path, device_name: str | None = None) -> bool:
    """Play one audio file (mp3 or wav) into the AirPod, blocking until it ends.

    Returns True only if the whole clip was played into the AirPod. On any problem
    it logs, stays silent (or stops), and returns False. It never raises and never
    plays through the MacBook speakers or the system default output.
    """
    path = Path(path)
    with _play_lock:
        try:
            device = find_airpod(device_name)
            if device is None:
                log.warning("No AirPod found (no output device matching %r); playing nothing.", device_name_wanted(device_name))
                return False
            try:
                audio, file_rate = _load(path)
            except Exception as error:  # noqa: BLE001 - unreadable audio means stay silent
                log.error("Not playing %s: %s", path, error)
                return False
            audio = _fit_channels(audio, min(device["max_output_channels"], 2))
            rate = _stream_rate(device, audio.shape[1], file_rate)
            if rate != file_rate:
                audio = _resample(audio, file_rate, rate)
            log.info("Playing %s into %r", path.name, device["name"])
            return _play_frames(device, audio, rate)
        except Exception as error:  # noqa: BLE001 - device errors must never reach the caller
            log.error("Playback of %s failed: %s", path, error)
            return False


def make_sample(folder: Path) -> Path:
    """Write a short fictional reminder as .mp3 into `folder`, using the macOS `say` voice."""
    say = shutil.which("say")
    if say is None:
        raise RuntimeError("the macOS `say` command is not available")
    wav = folder / "sample.wav"
    subprocess.run([say, "-o", str(wav), "--data-format=LEI16@22050", SAMPLE_TEXT], check=True)
    audio, sample_rate = sf.read(wav, dtype="float32")
    mp3 = folder / "sample.mp3"
    sf.write(mp3, audio, sample_rate, format="MP3")
    wav.unlink()
    return mp3


def print_devices(device_name: str | None) -> None:
    chosen = find_airpod(device_name)
    default_out = sd.default.device[1]
    print(f"Output devices (looking for {device_name_wanted(device_name)!r}):")
    for device in output_devices():
        marks = []
        if chosen is not None and device["index"] == chosen["index"]:
            marks.append("AIRPOD: reminders play here")
        if device["index"] == default_out:
            marks.append("system default, not used")
        if _is_built_in(device["name"]):
            marks.append("built-in, never used")
        note = f"  <- {'; '.join(marks)}" if marks else ""
        print(f"  [{device['index']}] {device['name']} ({device['max_output_channels']} ch, {int(device['default_samplerate'])} Hz){note}")
    if chosen is None:
        print("No AirPod found: play() would stay silent.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Play an audio file into the AirPod only.")
    parser.add_argument("file", nargs="?", help="audio file to play (mp3 or wav)")
    parser.add_argument("--device", help=f"part of the output device name (default: ${DEVICE_NAME_ENV} or {DEFAULT_DEVICE_NAME!r})")
    parser.add_argument("--list", action="store_true", help="list output devices and which one is the AirPod")
    parser.add_argument("--sample", action="store_true", help="make a short fictional reminder with `say` and play it")
    parser.add_argument("--repeat", type=int, default=1, help="play N times, waiting for Enter in between")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from argos_station.config import load_env  # .env may set ARGOS_AIRPOD_NAME

    load_env()

    if args.list:
        print_devices(args.device)
        return
    if args.sample == bool(args.file):
        parser.error("give either an audio file or --sample")

    with tempfile.TemporaryDirectory() as tmp:
        path = make_sample(Path(tmp)) if args.sample else Path(args.file)
        results = []
        for n in range(1, args.repeat + 1):
            if n > 1:
                input(f"Press Enter for play {n} of {args.repeat}...")
            ok = play(path, args.device)
            print("played" if ok else "silent (nothing played, or stopped)")
            results.append(ok)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
