"use client";

import { useActionState } from "react";
import { CircleAlert, CircleCheck } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { invite, type InviteState } from "./actions";

export function InviteForm() {
  const [state, formAction, pending] = useActionState<InviteState, FormData>(
    invite,
    {},
  );
  const failed = state.ok === false;

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="email">Email</Label>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Input
            id="email"
            name="email"
            type="email"
            autoComplete="off"
            placeholder="name@example.com"
            required
            // React resets the form after each submit; keep what was typed
            // when it didn't go through.
            defaultValue={state.ok ? "" : (state.email ?? "")}
            aria-invalid={failed ? true : undefined}
            aria-describedby={state.message ? "invite-result" : undefined}
            className="sm:max-w-md"
          />
          <Button type="submit" disabled={pending}>
            {pending ? "Sending…" : "Send invitation"}
          </Button>
        </div>
      </div>
      {state.message && (
        <Alert id="invite-result" variant={failed ? "danger" : "default"}>
          {failed ? (
            <CircleAlert strokeWidth={1.75} aria-hidden />
          ) : (
            <CircleCheck
              strokeWidth={1.75}
              className="text-success"
              aria-hidden
            />
          )}
          <AlertDescription>{state.message}</AlertDescription>
        </Alert>
      )}
    </form>
  );
}
