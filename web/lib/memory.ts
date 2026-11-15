// Memory rules shared by the dashboard, reminders and conversation
// processing (docs/memory.md). Plain logic: no database or network.

// memory_items.kind (docs/structure.md, "The contract").
export type MemoryKind = "fact" | "shared_memory" | "recent_event" | "follow_up";

export const RECENT_EVENT_DAYS = 30;

// A recent event older than RECENT_EVENT_DAYS is read as a fact. Computed
// when read; nothing rewrites rows (docs/structure.md).
export function shownKind(kind: MemoryKind, occurredOn: string, today: Date): MemoryKind {
  if (kind !== "recent_event") return kind;
  const cutoff = new Date(today);
  cutoff.setUTCDate(cutoff.getUTCDate() - RECENT_EVENT_DAYS);
  return occurredOn < cutoff.toISOString().slice(0, 10) ? "fact" : kind;
}
