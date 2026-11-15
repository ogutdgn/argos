import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { BackLink } from "@/components/back-link";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { getPatient } from "@/lib/supabase/people";
import { AddPatientForm } from "./add-patient-form";

export const metadata: Metadata = { title: "Add the patient · Argos" };

// The patient is not invited: a dashboard user adds their profile and records
// their voice here (docs/flows.md, "Dashboard"). There is at most one patient.
export default function AddPatientPage() {
  return (
    <>
      <BackLink href="/" label="All people" />
      <PageHeader
        title="Add the patient"
        description="Their name, a photo if you like, and a short recording of their voice."
      />
      <Suspense fallback={<p className="text-muted">Loading…</p>}>
        <PatientGate />
      </Suspense>
    </>
  );
}

async function PatientGate() {
  await connection();
  const patient = await getPatient();

  if (patient) {
    return (
      <Card>
        <CardContent className="flex flex-col gap-2">
          <h2 className="text-xl font-semibold">The patient is already here</h2>
          <p className="text-muted">
            Argos looks after one patient.{" "}
            <Link
              href={`/people/${patient.id}`}
              className="text-primary underline-offset-4 hover:underline"
            >
              See {patient.name}&apos;s page
            </Link>
            .
          </p>
        </CardContent>
      </Card>
    );
  }

  return <AddPatientForm />;
}
