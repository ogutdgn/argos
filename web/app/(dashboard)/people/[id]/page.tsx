import { Suspense } from "react";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { BookOpen } from "lucide-react";
import { BackLink } from "@/components/back-link";
import { PatientBadge, PersonAvatar } from "@/components/person-avatar";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate } from "@/lib/format";
import type { MemoryKind } from "@/lib/memory";
import { listMemoryItems, type MemoryItem } from "@/lib/supabase/memory";
import { getPatient, getPerson, type PersonWithMedia } from "@/lib/supabase/people";
import { MemoryItemRow } from "./memory-item";

// A person's page: profile, photo, voice sample and memory items grouped by
// kind (docs/memory.md). Every item can be edited or deleted.
export default function PersonPage({ params }: PageProps<"/people/[id]">) {
  return (
    <>
      <BackLink href="/" label="All people" />
      <Suspense fallback={<p className="text-muted">Loading…</p>}>
        <PersonDetails params={params} />
      </Suspense>
    </>
  );
}

async function PersonDetails({ params }: { params: Promise<{ id: string }> }) {
  await connection();
  const { id } = await params;
  const person = await getPerson(id);
  if (!person) notFound();

  const [items, patient] = await Promise.all([
    listMemoryItems(person.id),
    person.isPatient ? Promise.resolve(null) : getPatient(),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <ProfileHeader person={person} />
      <ProfileCard person={person} />
      <MemoryCard
        person={person}
        patientName={person.isPatient ? null : (patient?.name ?? null)}
        items={items}
      />
    </div>
  );
}

function ProfileHeader({ person }: { person: PersonWithMedia }) {
  return (
    <header className="flex items-center gap-5">
      <PersonAvatar
        name={person.name}
        photoUrl={person.photoUrl}
        className="size-20 text-2xl"
      />
      <div className="flex flex-col gap-1">
        <h1 className="text-3xl font-semibold">{person.name}</h1>
        <div className="flex flex-wrap items-center gap-2 text-muted">
          {person.isPatient ? <PatientBadge /> : person.relationship}
        </div>
      </div>
    </header>
  );
}

function ProfileCard({ person }: { person: PersonWithMedia }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Profile</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-4 sm:grid-cols-[180px_1fr]">
          <dt className="text-sm font-medium text-muted">Name</dt>
          <dd>{person.name}</dd>
          {!person.isPatient && (
            <>
              <dt className="text-sm font-medium text-muted">Relationship</dt>
              <dd>{person.relationship ?? "Not given"}</dd>
            </>
          )}
          <dt className="text-sm font-medium text-muted">Voice sample</dt>
          <dd>
            {person.voiceSampleUrl ? (
              <audio controls preload="none" src={person.voiceSampleUrl} className="w-full max-w-md" />
            ) : (
              <span className="text-muted">No voice sample yet</span>
            )}
          </dd>
          <dt className="text-sm font-medium text-muted">Added</dt>
          <dd>{formatDate(person.createdAt)}</dd>
        </dl>
      </CardContent>
    </Card>
  );
}

// Order on the page follows the hook priority in docs/memory.md, facts last.
const GROUPS: { kind: MemoryKind; title: string; description: (name: string, patient: string) => string }[] = [
  {
    kind: "follow_up",
    title: "To follow up on",
    description: () => "Plans, promises and topics from recent conversations.",
  },
  {
    kind: "recent_event",
    title: "Recent events",
    description: () => "News from the last 30 days. Older news is kept as a fact.",
  },
  {
    kind: "shared_memory",
    title: "Shared memories",
    description: (_, patient) => `Moments from the past with ${patient}.`,
  },
  {
    kind: "fact",
    title: "Facts",
    description: (name) => `Things that stay true about ${name}.`,
  },
];

function MemoryCard({
  person,
  patientName,
  items,
}: {
  person: PersonWithMedia;
  patientName: string | null;
  items: MemoryItem[];
}) {
  const patient = patientName ?? "the patient";

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Memory</h2>
        </CardTitle>
        <CardDescription>
          What Argos remembers about {person.name}. Edit or delete anything
          that isn&apos;t right.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-8">
        {items.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-card bg-subtle px-6 py-10 text-center">
            <span className="flex size-12 items-center justify-center rounded-full bg-primary-soft text-primary">
              <BookOpen size={20} strokeWidth={1.75} aria-hidden />
            </span>
            <h3 className="text-xl font-semibold">Nothing remembered yet</h3>
            <p className="max-w-md text-muted">
              {person.isPatient
                ? "Things visitors share about the patient will appear here."
                : `Memories appear here once ${person.name} registers or talks with ${patient}.`}
            </p>
          </div>
        ) : (
          GROUPS.map((group) => {
            // First-hand items first; second-hand ones stay in the background.
            const groupItems = items
              .filter((item) => item.shownKind === group.kind)
              .sort((a, b) => Number(a.toldBy !== null) - Number(b.toldBy !== null));
            if (groupItems.length === 0) return null;
            return (
              <section key={group.kind} className="flex flex-col gap-2">
                <div className="flex flex-col gap-0.5">
                  <h3 className="text-lg font-semibold">{group.title}</h3>
                  <p className="text-sm text-muted">
                    {group.description(person.name, patient)}
                  </p>
                </div>
                <ul className="divide-y divide-border border-y border-border">
                  {groupItems.map((item) => (
                    <MemoryItemRow
                      key={item.id}
                      item={item}
                      dateLabel={formatDate(item.occurredOn)}
                    />
                  ))}
                </ul>
              </section>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
