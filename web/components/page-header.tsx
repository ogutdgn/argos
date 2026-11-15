// Title and one-line description at the top of every dashboard page.
export function PageHeader({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <header className="mb-8 flex flex-col gap-1">
      <h1 className="text-3xl font-semibold">{title}</h1>
      {description && <p className="text-muted">{description}</p>}
    </header>
  );
}
