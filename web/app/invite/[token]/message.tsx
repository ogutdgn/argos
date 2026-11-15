import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";

// A calm one-card answer on the magic-link page: refusals, errors and the
// thank-you after submitting.
export function MessageCard({
  icon,
  title,
  text,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
}) {
  return (
    <Card className="mx-auto w-full max-w-[480px]">
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
    </Card>
  );
}

// Unknown, used and expired links all get the same answer.
export const LINK_USED = {
  title: "This link can no longer be used",
  text: "Invitation links work once and last for a week. Please ask your family to send you a new one.",
};
