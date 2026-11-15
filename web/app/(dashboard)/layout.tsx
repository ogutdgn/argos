import { Suspense } from "react";
import { requireDashboardUser } from "@/lib/supabase/auth";
import { logout } from "./actions";

// Shared layout for every dashboard page. Nothing below it renders until the
// visitor is confirmed as a dashboard user; everyone else goes to /login.
// web/proxy.ts already redirects logged-out visitors; this is the real check.
async function DashboardShell({ children }: { children: React.ReactNode }) {
  const user = await requireDashboardUser();

  return (
    <>
      <header>
        <strong>Argos</strong> · {user.name}{" "}
        <form action={logout} style={{ display: "inline" }}>
          <button type="submit">Log out</button>
        </form>
      </header>
      {children}
    </>
  );
}

export default function DashboardLayout({ children }: LayoutProps<"/">) {
  return (
    <Suspense fallback={<p>Loading…</p>}>
      <DashboardShell>{children}</DashboardShell>
    </Suspense>
  );
}
