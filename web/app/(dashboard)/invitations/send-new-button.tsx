"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { sendNewInvitation, type InviteState } from "./actions";

// On an expired invitation: sends a new link to the same email.
export function SendNewButton({ invitationId }: { invitationId: string }) {
  const [state, formAction, pending] = useActionState<InviteState, FormData>(
    sendNewInvitation,
    {},
  );

  return (
    <form action={formAction} className="flex flex-col items-start gap-1 sm:items-end">
      <input type="hidden" name="invitationId" value={invitationId} />
      <Button type="submit" variant="secondary" disabled={pending}>
        {pending ? "Sending…" : "Send a new invitation"}
      </Button>
      {state.ok === false && state.message && (
        <p role="alert" className="max-w-xs text-sm text-danger sm:text-right">
          {state.message}
        </p>
      )}
    </form>
  );
}
