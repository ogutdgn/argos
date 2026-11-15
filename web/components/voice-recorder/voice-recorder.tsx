"use client";

import { useEffect, useRef, useState } from "react";
import { CircleCheck, Mic, MicOff, RotateCcw, Square } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  analyzeVoice,
  MAX_SECONDS,
  MIN_SECONDS,
  PROBLEM_MESSAGES,
  type VoiceProblem,
} from "./checks";
import { VOICE_SCRIPT } from "./script";
import { encodeWav, resampleTo16k } from "./wav";

// Records a 20–30 second voice sample in the browser and checks it before it
// can be accepted. Shared by the dashboard (adding the patient) and the
// magic-link form. UI and client-side checks only: the parent uploads the
// accepted sample through web/lib/supabase/.
// Format and thresholds: docs/tech.md ("Voice samples").

export type VoiceSample = {
  blob: Blob; // audio/wav, 16 kHz mono 16-bit PCM
  durationSeconds: number;
};

type Status =
  | { kind: "idle" }
  | { kind: "starting" }
  | { kind: "recording" }
  | { kind: "checking" }
  | { kind: "retry"; problem: VoiceProblem }
  | { kind: "accepted"; url: string }
  | { kind: "blocked" } // microphone not allowed
  | { kind: "failed" }; // the browser could not record

// Collects raw microphone samples in 2048-sample chunks.
const CAPTURE_WORKLET = `
class ArgosCapture extends AudioWorkletProcessor {
  constructor() { super(); this.buf = new Float32Array(2048); this.n = 0; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) {
      for (let i = 0; i < ch.length; i++) {
        this.buf[this.n++] = ch[i];
        if (this.n === this.buf.length) {
          this.port.postMessage(this.buf);
          this.buf = new Float32Array(2048);
          this.n = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor("argos-capture", ArgosCapture);
`;

type Session = {
  context: AudioContext;
  stream: MediaStream;
  chunks: Float32Array[];
  length: number;
};

function formatSeconds(seconds: number) {
  const s = Math.floor(seconds);
  return `0:${String(s).padStart(2, "0")}`;
}

function join(chunks: Float32Array[], length: number) {
  const out = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}

export function VoiceRecorder({
  onChange,
  disabled = false,
}: {
  // Called with the accepted sample, or null when there is none (again).
  onChange: (sample: VoiceSample | null) => void;
  disabled?: boolean;
}) {
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [elapsed, setElapsed] = useState(0);
  const [level, setLevel] = useState(0); // 0–1, for the meter
  const session = useRef<Session | null>(null);
  const playbackUrl = useRef<string | null>(null);

  function release() {
    const current = session.current;
    session.current = null;
    if (!current) return null;
    current.stream.getTracks().forEach((track) => track.stop());
    void current.context.close();
    return current;
  }

  function clearPlayback() {
    if (playbackUrl.current) URL.revokeObjectURL(playbackUrl.current);
    playbackUrl.current = null;
  }

  // Stop the microphone and free the playback URL when the page goes away.
  useEffect(
    () => () => {
      release();
      clearPlayback();
    },
    [],
  );

  async function stop() {
    const current = release();
    if (!current) return;
    setStatus({ kind: "checking" });
    setLevel(0);

    const raw = join(current.chunks, current.length);
    const samples = await resampleTo16k(raw, current.context.sampleRate);
    const analysis = analyzeVoice(samples);

    if (analysis.problem) {
      setStatus({ kind: "retry", problem: analysis.problem });
      return;
    }
    const blob = encodeWav(samples);
    clearPlayback();
    playbackUrl.current = URL.createObjectURL(blob);
    setStatus({ kind: "accepted", url: playbackUrl.current });
    onChange({ blob, durationSeconds: analysis.durationSeconds });
  }

  async function start() {
    clearPlayback();
    onChange(null);
    setElapsed(0);
    setStatus({ kind: "starting" });

    let stream: MediaStream;
    try {
      // Raw microphone audio: the station hears the room without browser
      // clean-up, so the voiceprint should be built from the same kind of sound.
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });
    } catch {
      setStatus({ kind: "blocked" });
      return;
    }

    const context = new AudioContext();
    try {
      const moduleUrl = URL.createObjectURL(
        new Blob([CAPTURE_WORKLET], { type: "application/javascript" }),
      );
      await context.audioWorklet.addModule(moduleUrl);
      URL.revokeObjectURL(moduleUrl);
    } catch {
      stream.getTracks().forEach((track) => track.stop());
      void context.close();
      setStatus({ kind: "failed" });
      return;
    }

    const current: Session = { context, stream, chunks: [], length: 0 };
    session.current = current;

    const input = context.createMediaStreamSource(stream);
    const capture = new AudioWorkletNode(context, "argos-capture", {
      channelCount: 1,
      channelCountMode: "explicit",
    });
    const silent = context.createGain();
    silent.gain.value = 0; // keeps the node running without playing anything
    input.connect(capture).connect(silent).connect(context.destination);

    const maxLength = MAX_SECONDS * context.sampleRate;
    capture.port.onmessage = (event: MessageEvent<Float32Array>) => {
      if (session.current !== current) return;
      const chunk = event.data;
      current.chunks.push(chunk);
      current.length += chunk.length;

      let sum = 0;
      for (const s of chunk) sum += s * s;
      const db = 10 * Math.log10(sum / chunk.length + 1e-12);
      setLevel(Math.max(0, Math.min(1, (db + 60) / 50)));
      setElapsed(current.length / context.sampleRate);

      if (current.length >= maxLength) void stop();
    };

    setStatus({ kind: "recording" });
  }

  const recording = status.kind === "recording";
  const busy = status.kind === "starting" || status.kind === "checking";
  const remaining = Math.max(0, Math.ceil(MIN_SECONDS - elapsed));

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-card border border-border bg-subtle p-5">
        <p className="mb-2 text-sm font-medium text-muted">
          Please read this aloud, at an easy pace:
        </p>
        <p className="font-serif text-lg leading-relaxed text-ink">
          {VOICE_SCRIPT}
        </p>
      </div>

      {recording && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium text-ink">
              Recording {formatSeconds(elapsed)} of {formatSeconds(MAX_SECONDS)}
            </span>
            <span className="text-muted">
              {remaining > 0
                ? `Keep reading, ${remaining} more ${remaining === 1 ? "second" : "seconds"}`
                : "That's enough. Stop when you finish the text."}
            </span>
          </div>
          <div
            className="relative h-2 overflow-hidden rounded-full bg-subtle"
            role="progressbar"
            aria-label="Recording time"
            aria-valuemin={0}
            aria-valuemax={MAX_SECONDS}
            aria-valuenow={Math.floor(elapsed)}
          >
            <div
              className="h-full bg-primary"
              style={{ width: `${(elapsed / MAX_SECONDS) * 100}%` }}
            />
            <div
              className="absolute inset-y-0 w-0.5 bg-border-strong"
              style={{ left: `${(MIN_SECONDS / MAX_SECONDS) * 100}%` }}
              aria-hidden
            />
          </div>
          <div className="flex items-center gap-2" aria-hidden>
            <Mic size={16} strokeWidth={1.75} className="text-muted" />
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-subtle">
              <div
                className="h-full bg-success"
                style={{ width: `${level * 100}%` }}
              />
            </div>
          </div>
        </div>
      )}

      <div aria-live="polite" className="flex flex-col gap-3">
        {status.kind === "checking" && (
          <p className="text-sm text-muted">Listening back to the recording…</p>
        )}
        {status.kind === "retry" && (
          <Alert variant="warning">
            <RotateCcw strokeWidth={1.75} aria-hidden />
            <AlertDescription>{PROBLEM_MESSAGES[status.problem]}</AlertDescription>
          </Alert>
        )}
        {status.kind === "blocked" && (
          <Alert variant="warning">
            <MicOff strokeWidth={1.75} aria-hidden />
            <AlertDescription>
              Argos needs the microphone to hear the voice. Please allow it in
              the browser, then try again.
            </AlertDescription>
          </Alert>
        )}
        {status.kind === "failed" && (
          <Alert variant="warning">
            <MicOff strokeWidth={1.75} aria-hidden />
            <AlertDescription>
              Recording could not start in this browser. Please try again, or
              use a recent version of Chrome, Safari or Firefox.
            </AlertDescription>
          </Alert>
        )}
        {status.kind === "accepted" && (
          <div className="flex flex-col gap-3">
            <p className="flex items-center gap-2 text-sm font-medium text-success">
              <CircleCheck size={18} strokeWidth={1.75} aria-hidden />
              Thank you. The voice sample sounds clear.
            </p>
            <audio controls src={status.url} className="w-full" />
          </div>
        )}
      </div>

      <div>
        {recording ? (
          <Button type="button" variant="secondary" onClick={() => void stop()}>
            <Square strokeWidth={1.75} aria-hidden />
            Stop
          </Button>
        ) : (
          <Button
            type="button"
            variant="secondary"
            disabled={disabled || busy}
            onClick={() => void start()}
          >
            {status.kind === "idle" || status.kind === "starting" ? (
              <Mic strokeWidth={1.75} aria-hidden />
            ) : (
              <RotateCcw strokeWidth={1.75} aria-hidden />
            )}
            {status.kind === "idle" || status.kind === "starting"
              ? "Start recording"
              : status.kind === "blocked" || status.kind === "failed"
                ? "Try again"
                : "Record again"}
          </Button>
        )}
      </div>
    </div>
  );
}
