import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { connection } from "next/server";
import { ChevronRight, MessageCircle } from "lucide-react";
import { LocalTime } from "@/components/local-time";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { listConversations } from "@/lib/supabase/conversations";
import { duration, StatusBadge, visitorNames } from "./format";

export const metadata: Metadata = { title: "Conversations · Argos" };

// Every conversation, newest first (docs/flows.md, Flow C).
export default function ConversationsPage() {
  return (
    <>
      <PageHeader
        title="Conversations"
        description="Every visit Argos heard, with what was said and what it learned."
      />
      <Suspense fallback={<p className="text-muted">Loading conversations…</p>}>
        <ConversationList />
      </Suspense>
    </>
  );
}

async function ConversationList() {
  await connection();
  const conversations = await listConversations();

  if (conversations.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-primary-soft text-primary">
            <MessageCircle size={20} strokeWidth={1.75} aria-hidden />
          </span>
          <h2 className="text-xl font-semibold">No conversations yet</h2>
          <p className="max-w-md text-muted">
            When a visitor talks with the patient, the conversation appears here
            shortly after they leave.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="gap-0 py-2">
      <ul className="divide-y divide-border">
        {conversations.map((conversation) => (
          <li key={conversation.id}>
            <Link
              href={`/conversations/${conversation.id}`}
              className="flex min-h-11 items-center gap-4 px-6 py-3 transition-colors hover:bg-subtle focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
            >
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="flex flex-wrap items-center gap-2 font-medium text-ink">
                  {visitorNames(conversation.visitors)}
                  <StatusBadge status={conversation.status} />
                </span>
                <span className="text-sm text-muted">
                  <LocalTime iso={conversation.startedAt} /> ·{" "}
                  {duration(conversation.startedAt, conversation.endedAt).toLowerCase()}
                </span>
              </div>
              <ChevronRight size={18} strokeWidth={1.75} className="text-muted" aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
