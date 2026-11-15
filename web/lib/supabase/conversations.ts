import { createClient } from "./server";
import { shownKind, type MemoryKind } from "./memory";
import { isUuid } from "./people";

// Conversations for the dashboard (docs/flows.md, Flow C): who was there,
// the transcript, and the memory items taken from it. Tables:
// conversations, conversation_people, transcripts, memory_items
// (docs/structure.md, "The contract"). Reads use the signed-in user's
// client, so RLS applies. The station inserts conversations; W2.2 fills in
// the transcript and memory items.

export type ConversationStatus = "uploaded" | "processing" | "processed" | "failed";

export type ConversationVisitor = { id: string; name: string; relationship: string | null };

export type ConversationSummary = {
  id: string;
  startedAt: string;
  endedAt: string;
  status: ConversationStatus;
  visitors: ConversationVisitor[];
};

// A memory item taken from the conversation. It belongs to `person`: a
// visitor, or another registered person they talked about (second-hand,
// `toldBy` set).
export type LearnedItem = {
  id: string;
  person: { id: string; name: string };
  kind: MemoryKind; // as read today
  content: string;
  toldBy: { id: string; name: string } | null;
};

export type ConversationDetails = ConversationSummary & {
  transcript: string | null;
  learned: LearnedItem[];
};

type ConversationRow = {
  id: string;
  started_at: string;
  ended_at: string;
  status: ConversationStatus;
  conversation_people: { person: ConversationVisitor | null }[];
};

const COLUMNS =
  "id, started_at, ended_at, status, conversation_people(person:people(id, name, relationship))";

function toSummary(row: ConversationRow): ConversationSummary {
  return {
    id: row.id,
    startedAt: row.started_at,
    endedAt: row.ended_at,
    status: row.status,
    visitors: row.conversation_people
      .map((cp) => cp.person)
      .filter((p): p is ConversationVisitor => p !== null)
      .sort((a, b) => a.name.localeCompare(b.name)),
  };
}

// Every conversation, newest first.
export async function listConversations(): Promise<ConversationSummary[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("conversations")
    .select(COLUMNS)
    .order("started_at", { ascending: false });
  if (error) throw error;
  return (data as unknown as ConversationRow[]).map(toSummary);
}

type LearnedRow = {
  id: string;
  kind: MemoryKind;
  content: string;
  occurred_on: string;
  person: { id: string; name: string } | null;
  told_by: { id: string; name: string } | null;
};

// One conversation with its transcript and what was learned, or null.
// Call after connection(): it reads today's date.
export async function getConversation(id: string): Promise<ConversationDetails | null> {
  if (!isUuid(id)) return null;
  const supabase = await createClient();
  const [conversation, transcript, learned] = await Promise.all([
    supabase.from("conversations").select(COLUMNS).eq("id", id).maybeSingle(),
    supabase.from("transcripts").select("text").eq("conversation_id", id).maybeSingle(),
    supabase
      .from("memory_items")
      .select(
        "id, kind, content, occurred_on, person:people!person_id(id, name), told_by:people!told_by_person_id(id, name)",
      )
      .eq("source_conversation_id", id)
      .order("created_at"),
  ]);
  if (conversation.error) throw conversation.error;
  if (transcript.error) throw transcript.error;
  if (learned.error) throw learned.error;
  if (!conversation.data) return null;

  const today = new Date();
  return {
    ...toSummary(conversation.data as unknown as ConversationRow),
    transcript: transcript.data?.text ?? null,
    learned: (learned.data as unknown as LearnedRow[])
      .filter((row) => row.person !== null)
      .map((row) => ({
        id: row.id,
        person: row.person!,
        kind: shownKind(row.kind, row.occurred_on, today),
        content: row.content,
        toldBy: row.told_by,
      })),
  };
}
