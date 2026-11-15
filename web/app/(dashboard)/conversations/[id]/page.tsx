import { Suspense } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { BackLink } from "@/components/back-link";
import { LocalTime } from "@/components/local-time";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getConversation,
  type ConversationDetails,
  type LearnedItem,
} from "@/lib/supabase/conversations";
import type { MemoryKind } from "@/lib/memory";
import { duration, StatusBadge, visitorNames } from "../format";

// One conversation: who was there, what Argos learned, and the full
// transcript (docs/flows.md, Flow C). Second-hand items (what a visitor said
// about someone else) look like the others; only a small line says who told.
export default function ConversationPage({ params }: PageProps<"/conversations/[id]">) {
  return (
    <>
      <BackLink href="/conversations" label="All conversations" />
      <Suspense fallback={<p className="text-muted">Loading…</p>}>
        <ConversationDetailsView params={params} />
      </Suspense>
    </>
  );
}

async function ConversationDetailsView({ params }: { params: Promise<{ id: string }> }) {
  await connection();
  const { id } = await params;
  const conversation = await getConversation(id);
  if (!conversation) notFound();

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="flex flex-wrap items-center gap-3 text-3xl font-semibold">
          {visitorNames(conversation.visitors)}
          <StatusBadge status={conversation.status} />
        </h1>
        <p className="text-muted">
          <LocalTime iso={conversation.startedAt} /> ·{" "}
          {duration(conversation.startedAt, conversation.endedAt).toLowerCase()}
        </p>
      </header>

      {conversation.status === "processed" ? (
        <>
          <LearnedCard conversation={conversation} />
          <TranscriptCard transcript={conversation.transcript} />
        </>
      ) : (
        <NotReadyCard failed={conversation.status === "failed"} />
      )}
    </div>
  );
}

function NotReadyCard({ failed }: { failed: boolean }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold">
          {failed ? "This conversation couldn't be processed" : "Still being processed"}
        </h2>
        <p className="text-muted">
          {failed
            ? "Something went wrong while writing it out. The recording is kept, so nothing is lost."
            : "The transcript and what Argos learned will appear here in a few minutes."}
        </p>
      </CardContent>
    </Card>
  );
}

const KIND_LABEL: Record<MemoryKind, string> = {
  follow_up: "To follow up on",
  recent_event: "Recent event",
  shared_memory: "Shared memory",
  fact: "Fact",
};

// Visitors first (in name order), then anyone else whose memory got an item.
function groupByPerson(conversation: ConversationDetails) {
  const visitorIds = new Set(conversation.visitors.map((v) => v.id));
  const groups = new Map<string, { id: string; name: string; items: LearnedItem[] }>();
  for (const item of conversation.learned) {
    const group = groups.get(item.person.id) ?? { ...item.person, items: [] };
    group.items.push(item);
    groups.set(item.person.id, group);
  }
  return [...groups.values()]
    .map((group) => ({
      ...group,
      // First-hand first; second-hand stays in the background.
      items: group.items.sort((a, b) => Number(a.toldBy !== null) - Number(b.toldBy !== null)),
    }))
    .sort(
      (a, b) =>
        Number(!visitorIds.has(a.id)) - Number(!visitorIds.has(b.id)) ||
        a.name.localeCompare(b.name),
    );
}

function LearnedCard({ conversation }: { conversation: ConversationDetails }) {
  const groups = groupByPerson(conversation);

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>What Argos learned</h2>
        </CardTitle>
        <CardDescription>
          Added to each person&apos;s memory. Edit or delete anything on their page.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {groups.length === 0 ? (
          <p className="text-muted">Nothing new this time: it was a friendly chat.</p>
        ) : (
          groups.map((group) => (
            <section key={group.id} className="flex flex-col gap-2">
              <h3 className="text-lg font-semibold">
                <Link
                  href={`/people/${group.id}`}
                  className="rounded-control text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                >
                  {group.name}
                </Link>
              </h3>
              <ul className="divide-y divide-border border-y border-border">
                {group.items.map((item) => (
                  <li key={item.id} className="flex flex-col gap-1 py-3">
                    <p className="whitespace-pre-line text-ink">{item.content}</p>
                    <p className="text-sm text-muted">
                      {[KIND_LABEL[item.kind], item.toldBy ? `told by ${item.toldBy.name}` : null]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function TranscriptCard({ transcript }: { transcript: string | null }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Transcript</h2>
        </CardTitle>
        <CardDescription>Everything that was said, written out.</CardDescription>
      </CardHeader>
      <CardContent>
        {transcript ? (
          <p className="max-w-prose whitespace-pre-line text-ink">{transcript}</p>
        ) : (
          <p className="text-muted">No transcript was saved for this conversation.</p>
        )}
      </CardContent>
    </Card>
  );
}
