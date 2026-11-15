import { SAMPLE_RATE } from "./checks";

// Resamples mono audio to 16 kHz with the browser's own resampler.
export async function resampleTo16k(
  samples: Float32Array,
  sourceRate: number,
): Promise<Float32Array> {
  if (sourceRate === SAMPLE_RATE || samples.length === 0) return samples;

  const length = Math.ceil((samples.length * SAMPLE_RATE) / sourceRate);
  const offline = new OfflineAudioContext(1, length, SAMPLE_RATE);
  const buffer = offline.createBuffer(1, samples.length, sourceRate);
  buffer.copyToChannel(new Float32Array(samples), 0);

  const source = offline.createBufferSource();
  source.buffer = buffer;
  source.connect(offline.destination);
  source.start();

  const rendered = await offline.startRendering();
  return rendered.getChannelData(0);
}

// Mono 16-bit PCM WAV. 30 s at 16 kHz is about 960 KB.
export function encodeWav(samples: Float32Array, sampleRate = SAMPLE_RATE): Blob {
  const bytesPerSample = 2;
  const dataSize = samples.length * bytesPerSample;
  const view = new DataView(new ArrayBuffer(44 + dataSize));

  const text = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  };

  text(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true); // byte rate
  view.setUint16(32, bytesPerSample, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  text(36, "data");
  view.setUint32(40, dataSize, true);

  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }

  return new Blob([view.buffer], { type: "audio/wav" });
}
