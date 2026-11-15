import type { Metadata } from "next";
import { Suspense } from "react";
import { Clock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { getValidInvitation } from "@/lib/supabase/invitations";
import { InviteForm } from "./invite-form";
import { LINK_USED, MessageCard } from "./message";

export const metadata: Metadata = {
  title: "Argos",
  robots: { index: false, follow: false },
};

// The magic link from the invitation email (docs/flows.md, Flow A). Public:
// invited people have no account. Opening the link doesn't use it up; the
// form submit does (lib/supabase/registration.ts).
export default function InvitePage({ params }: PageProps<"/invite/[token]">) {
  return (
    <main className="min-h-dvh bg-canvas px-4 py-8 sm:py-12">
      <Suspense
        fallback={
          <Card className="mx-auto w-full max-w-[480px]">
            <CardContent className="text-muted">Loading…</CardContent>
          </Card>
        }
      >
        <InviteContent params={params} />
      </Suspense>
    </main>
  );
}

async function InviteContent({
  params,
}: Pick<PageProps<"/invite/[token]">, "params">) {
  const { token } = await params;
  let invitation;
  try {
    invitation = await getValidInvitation(token);
  } catch (err) {
    console.error(err);
    return (
      <MessageCard
        icon={<Clock size={20} strokeWidth={1.75} aria-hidden />}
        title="We couldn't open your invitation"
        text="Something went wrong on our side. Please try the link again in a little while."
      />
    );
  }

  if (!invitation) {
    return (
      <MessageCard
        icon={<Clock size={20} strokeWidth={1.75} aria-hidden />}
        {...LINK_USED}
      />
    );
  }

  return <InviteForm token={token} expiresOn={formatDate(invitation.expiresAt)} />;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}
