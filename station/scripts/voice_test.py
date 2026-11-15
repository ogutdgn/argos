"""S0.2 voice recognition test: can SpeechBrain tell our voices apart?

Usage (from station/scripts/):
    python voice_test.py enroll <name>          record a 25 s voice sample (read demo/voice-script.txt)
    python voice_test.py greet <name>           record a 4 s greeting; use "unknown" for someone not enrolled
    python voice_test.py evaluate               score all greetings and suggest a threshold
    python voice_test.py live --threshold T     speak and see who it thinks you are

Recordings are saved under voices/, which is git-ignored. Real voices never go into git.
"""

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
import torch
import torchaudio
from speechbrain.inference.speaker import EncoderClassifier

SAMPLE_RATE = 16000
HERE = Path(__file__).parent
ENROLL_DIR = HERE / "voices" / "enroll"
TEST_DIR = HERE / "voices" / "test"
MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
UNKNOWN = "unknown"


def record(path, seconds):
    """Record mono audio from the default mic (the MacBook mic) and save it as .wav."""
    input(f"Press Enter, then speak for {seconds} s...")
    print("Recording...")
    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, SAMPLE_RATE)
    print(f"Saved {path.relative_to(HERE)}")


def load_model():
    """Load the pretrained speaker model. Downloads it once on first run."""
    return EncoderClassifier.from_hparams(
        source=MODEL_SOURCE,
        savedir=str(HERE / "pretrained_models" / "ecapa"),
        run_opts={"device": "cpu"},
    )


def embed(model, path):
    """Turn a recording into a normalized voiceprint (192 numbers, length 1)."""
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    wav = torch.from_numpy(audio.mean(axis=1))
    if sr != SAMPLE_RATE:
        wav = torchaudio.functional.resample(wav, sr, SAMPLE_RATE)
    emb = model.encode_batch(wav.unsqueeze(0)).squeeze()
    return (emb / emb.norm()).numpy()


def load_enrolled(model):
    files = sorted(ENROLL_DIR.glob("*.wav"))
    if not files:
        sys.exit("No enrolled voices yet. Run: python voice_test.py enroll <name>")
    return {f.stem: embed(model, f) for f in files}


def best_match(voiceprint, enrolled):
    """Return the closest enrolled person, their score, and all scores (cosine similarity)."""
    scores = {name: float(np.dot(voiceprint, vp)) for name, vp in enrolled.items()}
    name = max(scores, key=scores.get)
    return name, scores[name], scores


def next_greeting_path(name):
    n = 1
    while (TEST_DIR / f"{name}_{n}.wav").exists():
        n += 1
    return TEST_DIR / f"{name}_{n}.wav"


def cmd_enroll(args):
    record(ENROLL_DIR / f"{args.name}.wav", args.seconds)


def cmd_greet(args):
    record(next_greeting_path(args.name), args.seconds)


def cmd_evaluate(args):
    model = load_model()
    enrolled = load_enrolled(model)
    greetings = sorted(TEST_DIR.glob("*.wav"))
    if not greetings:
        sys.exit("No greetings yet. Run: python voice_test.py greet <name>")

    results = []  # (file, label, best name, best score)
    genuine, impostor = [], []
    for path in greetings:
        label = path.stem.rsplit("_", 1)[0]
        if label != UNKNOWN and label not in enrolled:
            print(f"Skipping {path.name}: '{label}' is not enrolled (use '{UNKNOWN}' for strangers)")
            continue
        name, score, scores = best_match(embed(model, path), enrolled)
        results.append((path.name, label, name, score))
        for other, s in scores.items():
            (genuine if other == label else impostor).append(s)

    if not genuine or not impostor:
        sys.exit("Need greetings from enrolled people and at least 2 enrolled voices (or unknown greetings).")

    lowest_genuine, highest_impostor = min(genuine), max(impostor)
    midpoint = (lowest_genuine + highest_impostor) / 2
    # Silence over mistakes: never let an impostor score reach the threshold.
    threshold = args.threshold if args.threshold is not None else max(midpoint, highest_impostor + 0.01)

    correct = missed = wrong = silent_unknown = 0
    print(f"\n{'greeting':<22}{'label':<14}{'best match':<14}{'score':>7}  result")
    for file, label, name, score in results:
        speaks = score >= threshold
        if label == UNKNOWN:
            result = "WRONG NAME" if speaks else "silent (ok)"
            wrong += speaks
            silent_unknown += not speaks
        elif not speaks:
            result, missed = "silent (missed)", missed + 1
        elif name == label:
            result, correct = "correct", correct + 1
        else:
            result, wrong = "WRONG NAME", wrong + 1
        print(f"{file:<22}{label:<14}{name:<14}{score:>7.3f}  {result}")

    print(f"\nlowest genuine score : {lowest_genuine:.3f}")
    print(f"highest impostor score: {highest_impostor:.3f}")
    print(f"{'separable' if lowest_genuine > highest_impostor else 'OVERLAP: some greetings will be missed'}")
    print(f"threshold            : {threshold:.3f}")
    print(f"\ncorrect {correct} | missed {missed} | wrong names {wrong} (must be 0) | unknown kept silent {silent_unknown}")


def cmd_live(args):
    model = load_model()
    enrolled = load_enrolled(model)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "live.wav"
        record(path, args.seconds)
        name, score, _ = best_match(embed(model, path), enrolled)
    if score >= args.threshold:
        print(f"{name} ({score:.3f})")
    else:
        print(f"silent (best: {name} {score:.3f})")


def main():
    parser = argparse.ArgumentParser(description="S0.2 voice recognition test")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("enroll", help="record a voice sample")
    p.add_argument("name")
    p.add_argument("--seconds", type=float, default=25)
    p.set_defaults(func=cmd_enroll)

    p = sub.add_parser("greet", help="record a short greeting")
    p.add_argument("name", help=f"enrolled name, or '{UNKNOWN}' for someone not enrolled")
    p.add_argument("--seconds", type=float, default=4)
    p.set_defaults(func=cmd_greet)

    p = sub.add_parser("evaluate", help="score greetings and suggest a threshold")
    p.add_argument("--threshold", type=float, help="use this threshold instead of the suggested one")
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("live", help="speak and see who it thinks you are")
    p.add_argument("--threshold", type=float, required=True)
    p.add_argument("--seconds", type=float, default=4)
    p.set_defaults(func=cmd_live)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
