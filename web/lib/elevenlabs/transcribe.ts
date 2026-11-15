import "server-only";
import type { ScribeWord } from "@/lib/processing/transcript";

// Transcription: ElevenLabs Scribe, which also separates speakers
// (docs/tech.md). Returns Scribe's word list; lib/processing/transcript.ts
// turns it into speaker turns.

const ENDPOINT = "https://api.elevenlabs.io/v1/speech-to-text";
const MODEL = "scribe_v1";
const TIMEOUT_MS = 240_000; // a 30-minute visit takes a while

export function isTranscriptionConfigured() {
  return Boolean(process.env.ELEVENLABS_API_KEY);
}

// Audio file → words with speaker ids. Throws on any failure.
export async function transcribe(audio: Blob, fileName: string): Promise<ScribeWord[]> {
  const apiKey = process.env.ELEVENLABS_API_KEY;
  if (!apiKey) throw new Error("ELEVENLABS_API_KEY is not set");

  const form = new FormData();
  form.append("model_id", MODEL);
  form.append("file", audio, fileName);
  form.append("diarize", "true"); // who spoke when
  form.append("tag_audio_events", "false"); // no "(laughter)" in the text
  form.append("timestamps_granularity", "word");

  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: { "xi-api-key": apiKey },
    body: form,
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`ElevenLabs Scribe answered ${res.status}`);

  const data = (await res.json()) as { words?: ScribeWord[] };
  if (!Array.isArray(data.words)) throw new Error("ElevenLabs Scribe sent no words");
  return data.words;
}
