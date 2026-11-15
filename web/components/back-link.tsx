import Link from "next/link";
import { ArrowLeft } from "lucide-react";

// "All people" link at the top of a person's page and the add-patient page.
export function BackLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="mb-6 inline-flex min-h-11 items-center gap-2 rounded-control text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      <ArrowLeft size={16} strokeWidth={1.75} aria-hidden />
      {label}
    </Link>
  );
}
