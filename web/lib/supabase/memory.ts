import { createClient } from "./server";

// The memory_items table (docs/structure.md, "The contract"; rules in
// docs/memory.md). Dashboard reads and writes use the signed-in user's
// client, so RLS applies.

export type MemoryKind = "fact" | "shared_memory" | "recent_event" | "follow_up";

export type MemoryItem = {
  id: string;
  personId: string;
  kind: MemoryKind; // as stored
  // As read today: a recent_event older than 30 days is read as a fact.
  shownKind: MemoryKind;
  content: string;
  occurredOn: string; // YYYY-MM-DD
  fromConversation: boolean;
  toldBy: { id: string; name: string } | null; // set = second-hand
  createdAt: string;
};

type MemoryRow = {
  id: string;
  person_id: string;
  kind: MemoryKind;
  content: string;
  occurred_on: string;
  source_conversation_id: string | null;
  told_by_person_id: string | null;
  created_at: string;
  told_by: { id: string; name: string } | null;
};

export const RECENT_EVENT_DAYS = 30;

// Computed when read; nothing rewrites rows (docs/structure.md).
export function shownKind(kind: MemoryKind, occurredOn: string, today: Date): MemoryKind {
  if (kind !== "recent_event") return kind;
  const cutoff = new Date(today);
  cutoff.setUTCDate(cutoff.getUTCDate() - RECENT_EVENT_DAYS);
  return occurredOn < cutoff.toISOString().slice(0, 10) ? "fact" : kind;
}

// A person's memory items, newest first. Call after connection(): it reads
// today's date.
export async function listMemoryItems(personId: string): Promise<MemoryItem[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("memory_items")
    .select(
      "id, person_id, kind, content, occurred_on, source_conversation_id, told_by_person_id, created_at, told_by:people!told_by_person_id(id, name)",
    )
    .eq("person_id", personId)
    .order("occurred_on", { ascending: false })
    .order("created_at", { ascending: false });
  if (error) throw error;

  const today = new Date();
  return (data as unknown as MemoryRow[]).map((row) => ({
    id: row.id,
    personId: row.person_id,
    kind: row.kind,
    shownKind: shownKind(row.kind, row.occurred_on, today),
    content: row.content,
    occurredOn: row.occurred_on,
    fromConversation: row.source_conversation_id !== null,
    toldBy: row.told_by,
    createdAt: row.created_at,
  }));
}

// Returns the person the item belongs to, or null if there is no such item.
export async function updateMemoryItem(
  id: string,
  changes: { content: string; occurredOn: string },
): Promise<string | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("memory_items")
    .update({ content: changes.content, occurred_on: changes.occurredOn })
    .eq("id", id)
    .select("person_id")
    .maybeSingle();
  if (error) throw error;
  return data?.person_id ?? null;
}

// Returns the person the item belonged to, or null if there was no such item.
export async function deleteMemoryItem(id: string): Promise<string | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("memory_items")
    .delete()
    .eq("id", id)
    .select("person_id")
    .maybeSingle();
  if (error) throw error;
  return data?.person_id ?? null;
}
