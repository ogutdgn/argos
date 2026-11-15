"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogOut, Mail, Menu, MessageCircle, Users, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { logout } from "./actions";

// Sidebar on wide screens, a top bar with a menu button on phones.
// Layout rules: docs/design.md ("Layout").

// Until a page exists its item is shown but disabled. `match` says which
// paths count as that section, for the active state.
const NAV = [
  {
    label: "People",
    icon: Users,
    href: "/",
    match: (path: string) => path === "/" || path.startsWith("/people"),
  },
  { label: "Invitations", icon: Mail, href: null, match: null },
  { label: "Conversations", icon: MessageCircle, href: null, match: null },
] as const;

// Inside the dark sidebar the teal focus ring would be invisible (1.6:1),
// so the ring uses the sidebar text color instead.
const sidebarFocus =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sidebar-ink";

function Wordmark() {
  return (
    <span className="font-serif text-2xl font-semibold text-sidebar-ink">
      Argos
    </span>
  );
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <nav aria-label="Dashboard">
      <ul className="flex flex-col gap-1">
        {NAV.map(({ label, icon: Icon, href, match }) => (
          <li key={label}>
            {href ? (
              <Link
                href={href}
                onClick={onNavigate}
                aria-current={match?.(pathname) ? "page" : undefined}
                className={cn(
                  "flex min-h-11 items-center gap-3 rounded-control px-3 text-sidebar-ink transition-colors hover:bg-sidebar-active aria-[current=page]:bg-sidebar-active aria-[current=page]:font-medium",
                  sidebarFocus,
                )}
              >
                <Icon size={18} strokeWidth={1.75} aria-hidden />
                {label}
              </Link>
            ) : (
              <span
                aria-disabled="true"
                title="Coming soon"
                className="flex min-h-11 cursor-not-allowed items-center gap-3 rounded-control px-3 text-sidebar-muted"
              >
                <Icon size={18} strokeWidth={1.75} aria-hidden />
                {label}
              </span>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}

function Account({ userName }: { userName: string }) {
  return (
    <div className="flex flex-col gap-2 border-t border-sidebar-active pt-4">
      <p className="px-3 text-sm text-sidebar-muted">
        Signed in as{" "}
        <span className="font-medium text-sidebar-ink">{userName}</span>
      </p>
      <form action={logout}>
        <button
          type="submit"
          className={cn(
            "flex min-h-11 w-full cursor-pointer items-center gap-3 rounded-control px-3 text-sidebar-ink transition-colors hover:bg-sidebar-active",
            sidebarFocus,
          )}
        >
          <LogOut size={18} strokeWidth={1.75} aria-hidden />
          Log out
        </button>
      </form>
    </div>
  );
}

export function DashboardShell({
  userName,
  children,
}: {
  userName: string;
  children: React.ReactNode;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="min-h-dvh bg-canvas">
      {/* Wide screens: fixed sidebar. */}
      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col justify-between bg-sidebar px-4 py-6 lg:flex">
        <div className="flex flex-col gap-8">
          <div className="px-3">
            <Wordmark />
          </div>
          <Nav />
        </div>
        <Account userName={userName} />
      </aside>

      {/* Phones and tablets: top bar, menu opens below it. */}
      <div className="sticky top-0 z-10 bg-sidebar lg:hidden">
        <div className="flex items-center justify-between px-4 py-2">
          <Wordmark />
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-expanded={menuOpen}
            aria-controls="dashboard-menu"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            className={cn(
              "flex size-11 cursor-pointer items-center justify-center rounded-control text-sidebar-ink transition-colors hover:bg-sidebar-active",
              sidebarFocus,
            )}
          >
            {menuOpen ? (
              <X size={20} strokeWidth={1.75} aria-hidden />
            ) : (
              <Menu size={20} strokeWidth={1.75} aria-hidden />
            )}
          </button>
        </div>
        {menuOpen && (
          <div id="dashboard-menu" className="flex flex-col gap-4 px-4 pb-4">
            <Nav onNavigate={() => setMenuOpen(false)} />
            <Account userName={userName} />
          </div>
        )}
      </div>

      <main className="px-4 py-8 sm:px-8 lg:ml-60 lg:px-12 lg:py-12">
        <div className="mx-auto max-w-[1120px]">{children}</div>
      </main>
    </div>
  );
}
