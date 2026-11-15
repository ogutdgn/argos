import "server-only";

// Reminder voice: ElevenLabs text-to-speech (docs/tech.md). Returns an mp3,
// the format the station plays (reminder-audio bucket, 5 MB limit).

const MODEL = "eleven_multilingual_v2";
const OUTPUT_FORMAT = "mp3_44100_128";
const TIMEOUT_MS = 30_000;
const MAX_BYTES = 5 * 1024 * 1024; // the reminder-audio bucket limit

export function isSpeechConfigured() {
  return Boolean(process.env.ELEVENLABS_API_KEY && process.env.ELEVENLABS_VOICE_ID);
}

// Text → mp3 bytes. Throws on any failure.
export async function textToSpeech(text: string): Promise<Uint8Array> {
  const apiKey = process.env.ELEVENLABS_API_KEY;
  const voiceId = process.env.ELEVENLABS_VOICE_ID;
  if (!apiKey || !voiceId) throw new Error("ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID is not set");

  const res = await fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${encodeURIComponent(voiceId)}?output_format=${OUTPUT_FORMAT}`,
    {
      method: "POST",
      headers: {
        "xi-api-key": apiKey,
        "Content-Type": "application/json",
        Accept: "audio/mpeg",
      },
      body: JSON.stringify({ text, model_id: MODEL }),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    },
  );
  if (!res.ok) throw new Error(`ElevenLabs answered ${res.status}`);

  const audio = new Uint8Array(await res.arrayBuffer());
  if (audio.byteLength === 0) throw new Error("ElevenLabs sent no audio");
  if (audio.byteLength > MAX_BYTES) throw new Error("reminder audio is larger than 5 MB");
  return audio;
}
