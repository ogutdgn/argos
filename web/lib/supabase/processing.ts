import "server-only";
import type { ConversationContext, ExtractedItem, KnownPerson } from "@/lib/processing/learned";
import type { Segment } from "@/lib/processing/transcript";
import { createAdminClient } from "./admin";
import type { ConversationStatus } from "./conversations";

// Conversation processing (docs/structure.md, "Station → web handoff"). It
// runs for the station's call, with nobody signed in, so it uses the secret
// key and only touches the one conversation it was given.

export async function getConversationStatus(id: string): Promise<ConversationStatus | null> {
  const supabase = createAdminClient();
  const { data, error } = await supabase
    .from("conversations")
    .select("status")
    .eq("id", id)
    .maybeSingle();
  if (error) throw error;
  return (data?.status as ConversationStatus | undefined) ?? null;
}

// Moves an uploaded or failed conversation to "processing" in one
// conditional UPDATE, so two calls at once can't both start the work.
// False: another call got there first (or it is already done).
export async function claimConversation(id: string): Promise<boolean> {
  const supabase = createAdminClient();
  const { data, error } = await supabase
    .from("conversations")
    .update({ status: "processing", error: null })
    .eq("id", id)
    .in("status", ["uploaded", "failed"])
    .select("id");
  if (error) throw error;
  return data.length === 1;
}

export async function markProcessed(id: string): Promise<void> {
  const supabase = createAdminClient();
  const { error } = await supabase
    .from("conversations")
    .update({ status: "processed", error: null })
    .eq("id", id);
  if (error) throw error;
}

// The error is for the team only; the dashboard never shows it.
export async function markFailed(id: string, message: string): Promise<void> {
  const supabase = createAdminClient();
  const { error } = await supabase
    .from("conversations")
    .update({ status: "failed", error: message.slice(0, 500) })
    .eq("id", id);
  if (error) throw error;
}

type PersonRow = { id: string; name: string; relationship: string | null; is_patient: boolean };

function toKnown(row: PersonRow): KnownPerson {
  return { id: row.id, name: row.name, relationship: row.relationship, isPatient: row.is_patient };
}

export type ProcessingInputs = {
  recordingPath: string;
  endedAt: string;
  context: ConversationContext;
};

export async function loadProcessingInputs(id: string): Promise<ProcessingInputs> {
  const supabase = createAdminClient();
  const [conversation, visitors, people] = await Promise.all([
    supabase.from("conversations").select("recording_path, ended_at").eq("id", id).single(),
    supabase.from("conversation_people").select("person_id").eq("conversation_id", id),
    supabase.from("people").select("id, name, relationship, is_patient"),
  ]);
  if (conversation.error) throw conversation.error;
  if (visitors.error) throw visitors.error;
  if (people.error) throw people.error;

  const everyone = (people.data as PersonRow[]).map(toKnown);
  const visitorIds = new Set(visitors.data.map((v) => v.person_id as string));
  return {
    recordingPath: conversation.data.recording_path,
    endedAt: conversation.data.ended_at,
    context: {
      patient: everyone.find((p) => p.isPatient) ?? null,
      visitors: everyone.filter((p) => visitorIds.has(p.id) && !p.isPatient),
      people: everyone,
    },
  };
}

export async function downloadRecording(path: string): Promise<Blob> {
  const supabase = createAdminClient();
  const { data, error } = await supabase.storage.from("recordings").download(path);
  if (error) throw error;
  return data;
}

// Saves the transcript and replaces this conversation's memory items. A
// retry after a failure starts clean, so nothing is saved twice.
export async function saveResults(
  id: string,
  results: { text: string; segments: Segment[]; items: ExtractedItem[]; occurredOn: string },
): Promise<void> {
  const supabase = createAdminClient();

  const transcript = await supabase
    .from("transcripts")
    .upsert(
      { conversation_id: id, text: results.text, segments: results.segments },
      { onConflict: "conversation_id" },
    );
  if (transcript.error) throw transcript.error;

  const removed = await supabase.from("memory_items").delete().eq("source_conversation_id", id);
  if (removed.error) throw removed.error;

  if (results.items.length === 0) return;
  const inserted = await supabase.from("memory_items").insert(
    results.items.map((item) => ({
      person_id: item.personId,
      kind: item.kind,
      content: item.content,
      occurred_on: results.occurredOn,
      source_conversation_id: id,
      told_by_person_id: item.toldByPersonId,
    })),
  );
  if (inserted.error) throw inserted.error;
}
