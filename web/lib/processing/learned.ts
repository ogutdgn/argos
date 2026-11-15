// Checks the AI's answer about a conversation before anything is saved
// (docs/memory.md, "Important things from a conversation"). The model reads
// what people said, so its answer is never trusted: anything that breaks a
// rule below is dropped. Plain logic, so it can be checked with sample data.

export const MAX_ITEMS = 5; // per conversation (decided 2026-11-15, W2.2)
export const MAX_CONTENT = 500;

export type MemoryKind = "fact" | "shared_memory" | "recent_event" | "follow_up";
const KINDS: readonly MemoryKind[] = ["fact", "shared_memory", "recent_event", "follow_up"];

export type KnownPerson = {
  id: string;
  name: string;
  relationship: string | null;
  isPatient: boolean;
};

export type ConversationContext = {
  patient: KnownPerson | null;
  visitors: KnownPerson[]; // registered people heard in this conversation
  people: KnownPerson[]; // everyone registered, the patient and visitors included
};

export type LearnedItem = {
  personId: string; // whose memory it goes into
  toldByPersonId: string | null; // set = second-hand: the visitor who said it
  kind: MemoryKind;
  content: string;
};

export type CheckedExtraction = {
  speakerNames: Map<string, string>; // Scribe speaker id → name
  items: LearnedItem[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function list(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

// Speakers: only the patient and this conversation's visitors can be named,
// each at most once. A speaker named twice, or two speakers given the same
// person, are both left unnamed ("Speaker 1"): unsure means no name.
function checkSpeakers(
  raw: unknown,
  context: ConversationContext,
  present: string[],
): Map<string, string> {
  const allowed = new Map<string, string>();
  if (context.patient) allowed.set(context.patient.id, context.patient.name);
  for (const v of context.visitors) allowed.set(v.id, v.name);

  const claims = list(raw)
    .map((s) => ({ speaker: s.speaker_id, person: s.person_id }))
    .filter(
      (c): c is { speaker: string; person: string } =>
        typeof c.speaker === "string" &&
        present.includes(c.speaker) &&
        typeof c.person === "string" &&
        allowed.has(c.person),
    );
  const count = (key: "speaker" | "person", value: string) =>
    claims.filter((c) => c[key] === value).length;

  const names = new Map<string, string>();
  for (const c of claims) {
    if (count("speaker", c.speaker) === 1 && count("person", c.person) === 1) {
      names.set(c.speaker, allowed.get(c.person)!);
    }
  }
  return names;
}

// Items:
// - first-hand (told_by null): about a visitor of this conversation;
// - second-hand: said by a visitor about another registered person;
// - follow-ups (plans, promises, topics, what the patient enjoyed) are
//   first-hand only;
// - known kinds, non-empty text up to MAX_CONTENT, no duplicates;
// - at most MAX_ITEMS, in the model's order (most important first).
function checkItems(raw: unknown, context: ConversationContext): LearnedItem[] {
  const registered = new Set(context.people.map((p) => p.id));
  const visitors = new Set(context.visitors.map((v) => v.id));
  const seen = new Set<string>();
  const items: LearnedItem[] = [];

  for (const r of list(raw)) {
    const personId = r.person_id;
    const toldBy = r.told_by_person_id ?? null;
    const kind = r.kind;
    const content = typeof r.content === "string" ? r.content.replace(/\s+/g, " ").trim() : "";

    if (typeof personId !== "string" || !registered.has(personId)) continue;
    if (toldBy !== null && typeof toldBy !== "string") continue;
    if (!KINDS.includes(kind as MemoryKind)) continue;
    if (!content || content.length > MAX_CONTENT) continue;

    if (toldBy === null) {
      if (!visitors.has(personId)) continue;
    } else {
      if (!visitors.has(toldBy) || toldBy === personId) continue;
      if (kind === "follow_up") continue;
    }

    const key = `${personId}\n${content.toLowerCase()}`;
    if (seen.has(key)) continue;
    seen.add(key);

    items.push({ personId, toldByPersonId: toldBy, kind: kind as MemoryKind, content });
    if (items.length === MAX_ITEMS) break;
  }
  return items;
}

export function checkExtraction(
  raw: unknown,
  context: ConversationContext,
  presentSpeakers: string[],
): CheckedExtraction {
  const answer = isRecord(raw) ? raw : {};
  return {
    speakerNames: checkSpeakers(answer.speakers, context, presentSpeakers),
    items: checkItems(answer.items, context),
  };
}
