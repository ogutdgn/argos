import { Badge } from "@/components/ui/badge";
import type { ConversationStatus, ConversationVisitor } from "@/lib/supabase/conversations";

// How a conversation's status, visitors and length are shown. Shared by the
// conversation list and a conversation's page.

const STATUS = {
  uploaded: { label: "Being processed", variant: "default" },
  processing: { label: "Being processed", variant: "default" },
  processed: { label: "Ready", variant: "success" },
  failed: { label: "Couldn't be processed", variant: "muted" },
} as const;

export function StatusBadge({ status }: { status: ConversationStatus }) {
  const { label, variant } = STATUS[status];
  return <Badge variant={variant}>{label}</Badge>;
}

// "Odysseus and Penelope"; "A visitor" if their profile was deleted.
export function visitorNames(visitors: ConversationVisitor[]) {
  const names = visitors.map((v) => v.name);
  if (names.length === 0) return "A visitor";
  if (names.length === 1) return names[0];
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

// "About 25 minutes"; under a minute counts as a minute.
export function duration(startedAt: string, endedAt: string) {
  const minutes = Math.max(1, Math.round((Date.parse(endedAt) - Date.parse(startedAt)) / 60_000));
  if (minutes < 60) return `About ${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  const h = `${hours} ${hours === 1 ? "hour" : "hours"}`;
  return rest ? `About ${h} ${rest} min` : `About ${h}`;
}
