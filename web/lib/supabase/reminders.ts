import "server-only";
import { randomUUID } from "node:crypto";
import type { HookCandidate } from "@/lib/reminders/hook";
import { createAdminClient } from "./admin";
import { shownKind, type MemoryKind } from "./memory";

// The reminders table and the reminder-audio bucket (docs/structure.md, "The
// contract"). Reminders are made after a response has gone out (dashboard
// edits, registration) or by conversation processing, where nobody is signed
// in, so this uses the secret key. Callers pass a person id they have
// already checked.

const BUCKET = "reminder-audio";

export type ReminderInputs = {
  person: { id: string; name: string; relationship: string | null; isPatient: boolean };
  items: HookCandidate[];
  previousHookId: string | null;
};

type MemoryRow = {
  id: string;
  kind: MemoryKind;
  content: string;
  occurred_on: string;
  created_at: string;
  source_conversation_id: string | null;
  told_by: { name: string } | null;
};

// Everything needed to choose the next hook, or null if the person is gone.
export async function loadReminderInputs(personId: string): Promise<ReminderInputs | null> {
  const supabase = createAdminClient();
  const [person, memory, previous] = await Promise.all([
    supabase
      .from("people")
      .select("id, name, relationship, is_patient")
      .eq("id", personId)
      .maybeSingle(),
    supabase
      .from("memory_items")
      .select(
        "id, kind, content, occurred_on, created_at, source_conversation_id, told_by:people!told_by_person_id(name)",
      )
      .eq("person_id", personId),
    supabase
      .from("reminders")
      .select("hook_memory_item_id")
      .eq("person_id", personId)
      .order("created_at", { ascending: false })
      .limit(1)
      .maybeSingle(),
  ]);
  if (person.error) throw person.error;
  if (memory.error) throw memory.error;
  if (previous.error) throw previous.error;
  if (!person.data) return null;

  const today = new Date();
  return {
    person: {
      id: person.data.id,
      name: person.data.name,
      relationship: person.data.relationship,
      isPatient: person.data.is_patient,
    },
    items: (memory.data as unknown as MemoryRow[]).map((row) => ({
      id: row.id,
      kind: shownKind(row.kind, row.occurred_on, today),
      content: row.content,
      occurredOn: row.occurred_on,
      createdAt: row.created_at,
      sourceConversationId: row.source_conversation_id,
      toldByName: row.told_by?.name ?? null,
    })),
    previousHookId: previous.data?.hook_memory_item_id ?? null,
  };
}

// Uploads the audio, then inserts the row, so the station never sees a
// reminder without its audio. The row is the new current reminder.
export async function saveReminder(input: {
  personId: string;
  text: string;
  hookMemoryItemId: string | null;
  audio: Uint8Array;
}): Promise<void> {
  const supabase = createAdminClient();
  const id = randomUUID();
  const path = `${input.personId}/${id}.mp3`;

  const upload = await supabase.storage
    .from(BUCKET)
    .upload(path, input.audio, { contentType: "audio/mpeg", upsert: false });
  if (upload.error) throw upload.error;

  const { error } = await supabase.from("reminders").insert({
    id,
    person_id: input.personId,
    text: input.text,
    hook_memory_item_id: input.hookMemoryItemId,
    audio_path: path,
  });
  if (error) {
    await supabase.storage.from(BUCKET).remove([path]);
    throw error;
  }
}
