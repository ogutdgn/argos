import "server-only";
import { isAiConfigured } from "@/lib/ai/provider";
import { writeReminder } from "@/lib/ai/reminder";
import { isSpeechConfigured, textToSpeech } from "@/lib/elevenlabs/speech";
import { loadReminderInputs, saveReminder } from "@/lib/supabase/reminders";
import { pickHook } from "./hook";

// Makes a person's next reminder (docs/tasks.md, W2.1): choose the hook, write
// the sentence, make the audio, save both. Called whenever the person's
// memory changes, usually inside after() so the save that caused it returns
// at once:
//
//   after(() => regenerateReminder(personId));
//
// Never throws. On any failure it logs and changes nothing, so the station
// keeps playing the previous reminder (or stays silent if there is none).
export async function regenerateReminder(personId: string): Promise<void> {
  try {
    if (!isAiConfigured() || !isSpeechConfigured()) {
      console.warn(`Reminder for ${personId} not made: OpenAI or ElevenLabs keys are not set.`);
      return;
    }

    const inputs = await loadReminderInputs(personId);
    // The patient gets no reminder; a deleted person needs none.
    if (!inputs || inputs.person.isPatient || !inputs.person.relationship) return;
    const person = { name: inputs.person.name, relationship: inputs.person.relationship };

    const hook = pickHook(inputs.items, inputs.previousHookId);
    const text = await writeReminder(person, hook);
    const audio = await textToSpeech(text);

    await saveReminder({
      personId,
      text,
      hookMemoryItemId: hook?.id ?? null,
      audio,
    });
  } catch (err) {
    console.error(`Reminder for ${personId} not made; the previous one stays.`, err);
  }
}
