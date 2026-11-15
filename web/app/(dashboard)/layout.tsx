import { Suspense } from "react";
import { requireDashboardUser } from "@/lib/supabase/auth";
import { DashboardShell } from "./dashboard-shell";

// Shared layout for every dashboard page. Nothing below it renders until the
// visitor is confirmed as a dashboard user; everyone else goes to /login.
// web/proxy.ts already redirects logged-out visitors; this is the real check.
async function SignedIn({ children }: { children: React.ReactNode }) {
  const user = await requireDashboardUser();
  return <DashboardShell userName={user.name}>{children}</DashboardShell>;
}

export default function DashboardLayout({ children }: LayoutProps<"/">) {
  return (
    <Suspense
      fallback={
        <div className="min-h-dvh bg-canvas p-8 text-muted">Loading…</div>
      }
    >
      <SignedIn>{children}</SignedIn>
    </Suspense>
  );
}
