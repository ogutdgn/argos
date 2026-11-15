"use client";

import { useState, useTransition } from "react";
import { CircleAlert, Pencil, Trash2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { MemoryItem } from "@/lib/supabase/memory";
import { removeMemoryItem, saveMemoryItem } from "../actions";

type Mode = "view" | "edit" | "confirm-delete";

// One memory item with edit and delete. Second-hand items look the same as
// the others; only the small line under them says who told us.
export function MemoryItemRow({
  item,
  dateLabel,
}: {
  item: MemoryItem;
  dateLabel: string;
}) {
  const [mode, setMode] = useState<Mode>("view");
  const [content, setContent] = useState(item.content);
  const [occurredOn, setOccurredOn] = useState(item.occurredOn);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const contentId = `memory-${item.id}-content`;
  const dateId = `memory-${item.id}-date`;

  function cancel() {
    setContent(item.content);
    setOccurredOn(item.occurredOn);
    setError(null);
    setMode("view");
  }

  function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    startTransition(async () => {
      const result = await saveMemoryItem({ id: item.id, content, occurredOn });
      if (result.ok) setMode("view");
      else setError(result.error);
    });
  }

  function remove() {
    setError(null);
    startTransition(async () => {
      const result = await removeMemoryItem(item.id);
      if (!result.ok) setError(result.error);
    });
  }

  const meta = [
    dateLabel,
    item.toldBy ? `told by ${item.toldBy.name}` : null,
    item.fromConversation ? "from a conversation" : null,
  ].filter(Boolean);

  if (mode === "edit") {
    return (
      <li className="py-4">
        <form onSubmit={save} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor={contentId}>Memory</Label>
            <Textarea
              id={contentId}
              value={content}
              maxLength={2000}
              required
              autoFocus
              onChange={(e) => setContent(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2 sm:max-w-56">
            <Label htmlFor={dateId}>Date</Label>
            <Input
              id={dateId}
              type="date"
              value={occurredOn}
              required
              onChange={(e) => setOccurredOn(e.target.value)}
            />
          </div>
          {error && <ErrorNote message={error} />}
          <div className="flex gap-2">
            <Button type="submit" disabled={pending}>
              {pending ? "Saving…" : "Save"}
            </Button>
            <Button type="button" variant="ghost" onClick={cancel} disabled={pending}>
              Cancel
            </Button>
          </div>
        </form>
      </li>
    );
  }

  return (
    <li className="flex flex-col gap-3 py-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1">
          <p className="whitespace-pre-line text-ink">{item.content}</p>
          <p className="text-sm text-muted">{meta.join(" · ")}</p>
        </div>
        {mode === "view" && (
          <div className="flex shrink-0 gap-1">
            <Button type="button" variant="ghost" onClick={() => setMode("edit")}>
              <Pencil strokeWidth={1.75} aria-hidden />
              Edit
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="text-danger hover:bg-danger-soft"
              onClick={() => setMode("confirm-delete")}
            >
              <Trash2 strokeWidth={1.75} aria-hidden />
              Delete
            </Button>
          </div>
        )}
      </div>

      {mode === "confirm-delete" && (
        <div
          role="group"
          aria-label="Delete this memory"
          className="flex flex-col gap-3 rounded-control border border-danger/30 bg-danger-soft p-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <p className="text-sm text-ink">
            Delete this memory? It can&apos;t be brought back.
          </p>
          <div className="flex gap-2">
            <Button type="button" variant="danger" onClick={remove} disabled={pending}>
              {pending ? "Deleting…" : "Delete"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setMode("view")}
              disabled={pending}
            >
              Keep it
            </Button>
          </div>
        </div>
      )}
      {error && <ErrorNote message={error} />}
    </li>
  );
}

function ErrorNote({ message }: { message: string }) {
  return (
    <Alert variant="danger">
      <CircleAlert strokeWidth={1.75} aria-hidden />
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}
