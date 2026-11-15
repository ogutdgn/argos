import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

// A person's photo in a circle, or their initials when there is none.
export function PersonAvatar({
  name,
  photoUrl,
  className,
}: {
  name: string;
  photoUrl: string | null;
  className?: string;
}) {
  return (
    <Avatar className={cn("size-12", className)}>
      {photoUrl && <AvatarImage src={photoUrl} alt="" />}
      <AvatarFallback aria-hidden>{initials(name)}</AvatarFallback>
    </Avatar>
  );
}

// "Patient" badge in warm bronze. Accent text only on surface or canvas,
// never on primary-soft (contrast, docs/design.md).
export function PatientBadge() {
  return (
    <span className="inline-flex items-center rounded-full border border-accent/40 bg-surface px-2.5 py-0.5 text-sm font-medium text-accent">
      Patient
    </span>
  );
}
