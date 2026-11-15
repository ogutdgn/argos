import { Suspense } from "react";
import Link from "next/link";
import { connection } from "next/server";
import { ChevronRight, Mic, Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { PatientBadge, PersonAvatar } from "@/components/person-avatar";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { listPeople } from "@/lib/supabase/people";

// Dashboard home: everyone in the system, the patient first.
export default function PeoplePage() {
  return (
    <>
      <PageHeader
        title="People"
        description="Everyone Argos helps you recognize, and what it remembers about them."
      />
      <Suspense fallback={<p className="text-muted">Loading people…</p>}>
        <PeopleList />
      </Suspense>
    </>
  );
}

async function PeopleList() {
  await connection();
  const people = await listPeople();
  const hasPatient = people.some((p) => p.isPatient);
  const visitors = people.filter((p) => !p.isPatient);

  return (
    <div className="flex flex-col gap-6">
      {!hasPatient && <AddPatientCard />}

      {people.length > 0 && (
        <Card className="gap-0 py-2">
          <ul className="divide-y divide-border">
            {people.map((person) => (
              <li key={person.id}>
                <Link
                  href={`/people/${person.id}`}
                  className="flex min-h-11 items-center gap-4 px-6 py-3 transition-colors hover:bg-subtle focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
                >
                  <PersonAvatar name={person.name} photoUrl={person.photoUrl} />
                  <div className="flex min-w-0 flex-1 flex-col">
                    <span className="flex flex-wrap items-center gap-2 font-medium text-ink">
                      {person.name}
                      {person.isPatient && <PatientBadge />}
                    </span>
                    {person.relationship && (
                      <span className="text-sm text-muted">
                        {person.relationship}
                      </span>
                    )}
                  </div>
                  <ChevronRight
                    size={18}
                    strokeWidth={1.75}
                    className="text-muted"
                    aria-hidden
                  />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {visitors.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
            <span className="flex size-12 items-center justify-center rounded-full bg-primary-soft text-primary">
              <Users size={20} strokeWidth={1.75} aria-hidden />
            </span>
            <h2 className="text-xl font-semibold">No visitors here yet</h2>
            <p className="max-w-md text-muted">
              Invite the first person. They add their voice and a few memories,
              and Argos takes it from there.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function AddPatientCard() {
  return (
    <Card>
      <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <span className="flex size-12 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary">
          <Mic size={20} strokeWidth={1.75} aria-hidden />
        </span>
        <div className="flex flex-1 flex-col gap-1">
          <h2 className="text-xl font-semibold">Add the patient</h2>
          <p className="text-muted">
            Record their voice once, so Argos never mistakes it for a visitor.
          </p>
        </div>
        <Button asChild>
          <Link href="/people/add-patient">Add the patient</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
