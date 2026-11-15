// Chooses the one memory item a reminder talks about (docs/memory.md,
// "Choosing the conversation hook"). Plain logic, no database or network, so
// it can be checked with sample data.
//
// Order, highest first:
// 1. follow-ups from the person's latest conversation
// 2. recent events (30 days or newer)
// 3. shared memories
// 4. older follow-ups
// 5. facts (including recent events older than 30 days)
// Within a group: first-hand before second-hand, then newest first.
// The previous reminder's hook is never chosen again. Nothing left → null,
// and the reminder is name + relationship only.

export type HookKind = "fact" | "shared_memory" | "recent_event" | "follow_up";

export type HookCandidate = {
  id: string;
  kind: HookKind; // as read today: a stale recent_event is already "fact"
  content: string;
  occurredOn: string; // YYYY-MM-DD
  createdAt: string; // ISO timestamp
  sourceConversationId: string | null;
  toldByName: string | null; // set = second-hand
};

function newestFirst(a: HookCandidate, b: HookCandidate) {
  const secondHand = Number(a.toldByName !== null) - Number(b.toldByName !== null);
  if (secondHand !== 0) return secondHand;
  if (a.occurredOn !== b.occurredOn) return a.occurredOn < b.occurredOn ? 1 : -1;
  if (a.createdAt !== b.createdAt) return a.createdAt < b.createdAt ? 1 : -1;
  return 0;
}

// The conversation the newest follow-up came from. Follow-ups are only made
// when a conversation is processed, so this is the latest conversation that
// left anything to follow up on.
function latestFollowUpConversation(items: HookCandidate[]): string | null {
  let newest: HookCandidate | null = null;
  for (const item of items) {
    if (item.kind !== "follow_up" || item.sourceConversationId === null) continue;
    if (!newest || item.createdAt > newest.createdAt) newest = item;
  }
  return newest?.sourceConversationId ?? null;
}

export function pickHook(
  items: HookCandidate[],
  previousHookId: string | null,
): HookCandidate | null {
  const candidates = items.filter((item) => item.id !== previousHookId);
  const latest = latestFollowUpConversation(items);

  const groups: ((item: HookCandidate) => boolean)[] = [
    (item) => item.kind === "follow_up" && latest !== null && item.sourceConversationId === latest,
    (item) => item.kind === "recent_event",
    (item) => item.kind === "shared_memory",
    (item) => item.kind === "follow_up",
    (item) => item.kind === "fact",
  ];

  for (const inGroup of groups) {
    const group = candidates.filter(inGroup).sort(newestFirst);
    if (group.length > 0) return group[0];
  }
  return null;
}
