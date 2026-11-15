import * as React from "react";

import { cn } from "@/lib/utils";

// shadcn/ui textarea, themed with the Argos tokens (docs/design.md).
function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex min-h-24 w-full min-w-0 rounded-control border border-border-strong bg-surface px-3 py-2 text-base text-ink transition-colors placeholder:text-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-60 aria-invalid:border-danger",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
