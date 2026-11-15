// Turns ElevenLabs Scribe's word list into speaker turns and the transcript
// text shown in the dashboard. Plain logic, no network, so it can be checked
// with sample data.

// One item of Scribe's `words`: a word, the space after it, or a sound.
export type ScribeWord = {
  text: string;
  start?: number; // seconds
  end?: number;
  type: "word" | "spacing" | "audio_event";
  speaker_id?: string | null;
};

// Stored in transcripts.segments. `name` is set when the speaker is known
// (the patient or a visitor), else null.
export type Segment = {
  speaker_id: string;
  name: string | null;
  start: number;
  end: number;
  text: string;
};

const UNKNOWN_SPEAKER = "unknown";

// Consecutive words of the same speaker become one turn. Sounds (laughter,
// music) are left out.
export function toSegments(words: ScribeWord[]): Segment[] {
  const segments: Segment[] = [];
  for (const word of words) {
    if (word.type === "audio_event") continue;
    const speaker = word.speaker_id || UNKNOWN_SPEAKER;
    const last = segments[segments.length - 1];
    if (word.type === "spacing") {
      if (last) last.text += word.text;
      continue;
    }
    if (last && last.speaker_id === speaker) {
      last.text += word.text;
      last.end = word.end ?? last.end;
    } else {
      segments.push({
        speaker_id: speaker,
        name: null,
        start: word.start ?? last?.end ?? 0,
        end: word.end ?? word.start ?? last?.end ?? 0,
        text: word.text,
      });
    }
  }
  return segments
    .map((s) => ({ ...s, text: s.text.replace(/\s+/g, " ").trim() }))
    .filter((s) => s.text.length > 0);
}

// The speakers in order of first appearance.
export function speakerIds(segments: Segment[]): string[] {
  return [...new Set(segments.map((s) => s.speaker_id))];
}

// Fills in the names that are known.
export function nameSegments(segments: Segment[], names: Map<string, string>): Segment[] {
  return segments.map((s) => ({ ...s, name: names.get(s.speaker_id) ?? null }));
}

// "Odysseus: …" per turn, a blank line between turns. A speaker without a
// name is "Speaker 1", "Speaker 2"… in order of first appearance.
export function transcriptText(segments: Segment[]): string {
  const order = speakerIds(segments);
  return segments
    .map((s) => `${s.name ?? `Speaker ${order.indexOf(s.speaker_id) + 1}`}: ${s.text}`)
    .join("\n\n");
}

// For the AI: one line per turn, with Scribe's speaker ids, so it can say
// who each speaker is.
export function transcriptForModel(segments: Segment[]): string {
  return segments.map((s) => `[${s.speaker_id}] ${s.text}`).join("\n");
}
