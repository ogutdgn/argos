import { Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";

// Dashboard home. An empty state for now: people and memory come in W1.2,
// invitations in W1.3.
export default function DashboardHome() {
  return (
    <>
      <PageHeader
        title="People"
        description="Everyone Argos helps you recognize, and what it remembers about them."
      />
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-primary-soft text-primary">
            <Users size={20} strokeWidth={1.75} aria-hidden />
          </span>
          <h2 className="text-xl font-semibold">No one here yet</h2>
          <p className="max-w-md text-muted">
            Invite the first person. They add their voice and a few memories,
            and Argos takes it from there.
          </p>
        </CardContent>
      </Card>
    </>
  );
}
