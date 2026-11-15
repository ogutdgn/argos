import "server-only";
import { extractFromTranscript } from "@/lib/ai/extract";
import { transcribe } from "@/lib/elevenlabs/transcribe";
import { regenerateReminder } from "@/lib/reminders/regenerate";
import {
  downloadRecording,
  loadProcessingInputs,
  markFailed,
  markProcessed,
  saveResults,
} from "@/lib/supabase/processing";
import { checkExtraction } from "./learned";
import {
  nameSegments,
  speakerIds,
  toSegments,
  transcriptForModel,
  transcriptText,
} from "./transcript";

// Processes one conversation the station uploaded (docs/flows.md, Flow C):
// transcribe → save the transcript and what was learned → new reminders.
// Called by app/api/conversations/process/route.ts inside after(), once the
// conversation is claimed ("processing"). Never throws: the conversation
// ends "processed" or "failed", and a failed one can be sent again.
export async function processConversation(id: string): Promise<void> {
  let reminderFor: string[];
  try {
    const { recordingPath, endedAt, context } = await loadProcessingInputs(id);

    const audio = await downloadRecording(recordingPath);
    const segments = toSegments(await transcribe(audio, recordingPath));

    const answer =
      segments.length > 0
        ? await extractFromTranscript(transcriptForModel(segments), context, endedAt.slice(0, 10))
        : {};
    const { speakerNames, items } = checkExtraction(answer, context, speakerIds(segments));

    const named = nameSegments(segments, speakerNames);
    await saveResults(id, {
      text: transcriptText(named),
      segments: named,
      items,
      occurredOn: endedAt.slice(0, 10),
    });
    await markProcessed(id);

    // Every visitor's reminder changes, even with nothing new: the hook
    // that just played must not play again next time. Anyone else who got
    // a second-hand item gets a new one too.
    reminderFor = [
      ...new Set([...context.visitors.map((v) => v.id), ...items.map((i) => i.personId)]),
    ];
  } catch (err) {
    console.error(`Conversation ${id} could not be processed`, err);
    const message = err instanceof Error ? err.message : "unknown error";
    await markFailed(id, message).catch((e) =>
      console.error(`Conversation ${id}: could not mark it failed`, e),
    );
    return;
  }

  // Reminders after the conversation is saved: a reminder that fails keeps
  // the previous one (regenerateReminder never throws) and never fails the
  // conversation. The patient gets none.
  for (const personId of reminderFor) {
    await regenerateReminder(personId);
  }
}
