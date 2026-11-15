import type { Metadata } from "next";
import { Suspense } from "react";
import { Clock, Mail } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { getValidInvitation } from "@/lib/supabase/invitations";

export const metadata: Metadata = {
  title: "Argos",
  robots: { index: false, follow: false },
};

// The magic link from the invitation email (docs/flows.md, Flow A). Public:
// invited people have no account. Opening the link doesn't use it up; the
// form submit does (markInvitationUsed in lib/supabase/invitations.ts).
// W1.4 replaces the placeholder with the registration form.
export default function InvitePage({ params }: PageProps<"/invite/[token]">) {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-canvas px-4 py-12">
      <Card className="w-full max-w-[480px]">
        <Suspense
          fallback={<CardContent className="text-muted">Loading…</CardContent>}
        >
          <InviteContent params={params} />
        </Suspense>
      </Card>
    </main>
  );
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
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
      <Message
        icon={<Clock size={20} strokeWidth={1.75} aria-hidden />}
        title="We couldn't open your invitation"
        text="Something went wrong on our side. Please try the link again in a little while."
      />
    );
  }

  // Unknown, used and expired links all get the same calm answer.
  if (!invitation) {
    return (
      <Message
        icon={<Clock size={20} strokeWidth={1.75} aria-hidden />}
        title="This link can no longer be used"
        text="Invitation links work once and last for a week. Please ask your family to send you a new one."
      />
    );
  }

  return (
    <Message
      icon={<Mail size={20} strokeWidth={1.75} aria-hidden />}
      title="Welcome to Argos"
      text={`The form to add yourself is on its way. Your link is ready and keeps working until ${formatDate(invitation.expiresAt)}.`}
    />
  );
}

function Message({
  icon,
  title,
  text,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
}) {
  return (
    <>
      <CardHeader className="gap-4">
        <span className="font-serif text-2xl font-semibold">Argos</span>
        <span className="flex size-12 items-center justify-center rounded-full bg-primary-soft text-primary">
          {icon}
        </span>
        <h1 className="text-3xl font-semibold">{title}</h1>
      </CardHeader>
      <CardContent>
        <CardDescription>{text}</CardDescription>
      </CardContent>
    </>
  );
}
