// Checks a recorded voice sample before it can be accepted.
// The numbers are documented in docs/edge-cases.md ("Bad voice sample") and
// docs/tech.md ("Voice samples"); change them there too.

export const SAMPLE_RATE = 16_000; // the sample is stored as 16 kHz mono WAV
export const MIN_SECONDS = 20; // shorter recordings are "too short"
export const MAX_SECONDS = 30; // recording stops on its own here
export const MIN_SPEECH_SECONDS = 10; // less speech than this is "too short"
export const MIN_LEVEL_DBFS = -40; // speech level below this is "too quiet"
export const MIN_SNR_DB = 15; // speech this close to the background is "noisy"

const FRAME = 480; // 30 ms at 16 kHz
const SPEECH_BELOW_PEAK_DB = 20; // a frame is speech if within 20 dB of the level…
const SPEECH_ABOVE_NOISE_DB = 10; // …and at least 10 dB above the background

export type VoiceProblem = "too_short" | "too_quiet" | "noisy";

export type VoiceAnalysis = {
  durationSeconds: number;
  speechSeconds: number;
  levelDbfs: number; // 95th percentile of 30 ms frame loudness
  noiseDbfs: number; // 10th percentile: the background between words
  problem: VoiceProblem | null;
};

function percentile(sorted: Float64Array, p: number) {
  if (sorted.length === 0) return -Infinity;
  const index = Math.min(sorted.length - 1, Math.floor(p * sorted.length));
  return sorted[index];
}

// `samples` is mono audio at SAMPLE_RATE, values in [-1, 1].
export function analyzeVoice(samples: Float32Array): VoiceAnalysis {
  const durationSeconds = samples.length / SAMPLE_RATE;
  const frameCount = Math.floor(samples.length / FRAME);
  const frameDb = new Float64Array(frameCount);

  for (let f = 0; f < frameCount; f++) {
    let sum = 0;
    for (let i = f * FRAME; i < (f + 1) * FRAME; i++) sum += samples[i] * samples[i];
    frameDb[f] = 10 * Math.log10(sum / FRAME + 1e-12);
  }

  const sorted = frameDb.slice().sort();
  const levelDbfs = percentile(sorted, 0.95);
  const noiseDbfs = percentile(sorted, 0.1);

  const speechFloor = Math.max(
    levelDbfs - SPEECH_BELOW_PEAK_DB,
    noiseDbfs + SPEECH_ABOVE_NOISE_DB,
  );
  let speechFrames = 0;
  for (const db of frameDb) if (db >= speechFloor) speechFrames++;
  const speechSeconds = (speechFrames * FRAME) / SAMPLE_RATE;

  let problem: VoiceProblem | null = null;
  if (durationSeconds < MIN_SECONDS) problem = "too_short";
  else if (levelDbfs < MIN_LEVEL_DBFS) problem = "too_quiet";
  else if (levelDbfs - noiseDbfs < MIN_SNR_DB) problem = "noisy";
  else if (speechSeconds < MIN_SPEECH_SECONDS) problem = "too_short";

  return { durationSeconds, speechSeconds, levelDbfs, noiseDbfs, problem };
}

// Warm, never corrective: say what would help, not what went wrong.
export const PROBLEM_MESSAGES: Record<VoiceProblem, string> = {
  too_short:
    "That was a little short. Please read the whole text once more, at an easy pace.",
  too_quiet:
    "The voice came through very softly. Please move a little closer to the microphone and read it once more.",
  noisy:
    "There was a lot of sound in the background. Please find a quieter spot and read it once more.",
};
