import type { Metadata } from "next";
import { Suspense } from "react";
import { Mail } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { formatDate } from "@/lib/format";
import { listInvitations, type Invitation } from "@/lib/supabase/invitations";
import { InviteForm } from "./invite-form";
import { SendNewButton } from "./send-new-button";

export const metadata: Metadata = { title: "Invitations · Argos" };

// Invite a person by email (docs/flows.md, Flow A). Each invitation is a
// one-time link that lasts a week; an expired one can be sent again.
export default function InvitationsPage() {
  return (
    <>
      <PageHeader
        title="Invitations"
        description="Invite family and friends by email, so they can add themselves to Argos."
      />
      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <h2 className="text-xl font-semibold">Invite someone</h2>
            <CardDescription>
              They get a personal link to add their name, a few memories, a
              photo and their voice. The link works once and lasts a week.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <InviteForm />
          </CardContent>
        </Card>
        <Suspense
          fallback={
            <Card>
              <CardContent className="text-muted">
                Loading invitations…
              </CardContent>
            </Card>
          }
        >
          <InvitationList />
        </Suspense>
      </div>
    </>
  );
}

const BADGE = {
  pending: { label: "Pending", variant: "default" },
  used: { label: "Used", variant: "success" },
  expired: { label: "Expired", variant: "muted" },
} as const;

function detail(invitation: Invitation) {
  const sent = `Sent ${formatDate(invitation.createdAt)}`;
  switch (invitation.status) {
    case "pending":
      return `${sent} · Link valid until ${formatDate(invitation.expiresAt)}`;
    case "used":
      return `${sent} · Added themselves ${formatDate(invitation.usedAt!)}`;
    case "expired":
      return `${sent} · Link expired ${formatDate(invitation.expiresAt)}`;
  }
}

async function InvitationList() {
  const invitations = await listInvitations();

  if (invitations.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-6 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-primary-soft text-primary">
            <Mail size={20} strokeWidth={1.75} aria-hidden />
          </span>
          <h2 className="text-xl font-semibold">No invitations yet</h2>
          <p className="max-w-md text-muted">
            Invite the people who visit most often first. You&apos;ll see here when
            each of them has added themselves.
          </p>
        </CardContent>
      </Card>
    );
  }

  // Offer "Send a new invitation" only on the newest invitation for an
  // email, so an older expired one doesn't ask again once a new link exists.
  // The list is newest first, so the first row per email is the newest.
  const newestIds = new Set<string>();
  const seen = new Set<string>();
  for (const invitation of invitations) {
    if (seen.has(invitation.email)) continue;
    seen.add(invitation.email);
    newestIds.add(invitation.id);
  }

  return (
    <Card className="gap-4 pb-2">
      <CardHeader>
        <h2 className="text-xl font-semibold">Sent invitations</h2>
      </CardHeader>
      <ul className="divide-y divide-border border-t border-border">
        {invitations.map((invitation) => {
          const badge = BADGE[invitation.status];
          return (
            <li
              key={invitation.id}
              className="flex flex-col gap-3 px-6 py-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex min-w-0 flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="truncate font-medium">
                    {invitation.email}
                  </span>
                  <Badge variant={badge.variant}>{badge.label}</Badge>
                </div>
                <p className="text-sm text-muted">{detail(invitation)}</p>
              </div>
              {invitation.status === "expired" &&
                newestIds.has(invitation.id) && (
                  <SendNewButton invitationId={invitation.id} />
                )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
