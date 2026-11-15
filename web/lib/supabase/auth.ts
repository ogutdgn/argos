import { redirect } from "next/navigation";
import { createClient } from "./server";

// Dashboard login. A dashboard user is a Supabase Auth account that also has
// a row in public.users (same id). Accounts and rows are added by hand in
// Supabase; there is no sign-up. Steps: web/README.md ("Dashboard users").

export type DashboardUser = { id: string; name: string };

// The signed-in dashboard user, or null. RLS lets a dashboard user read
// public.users, so a signed-in account without a row reads nothing.
async function findDashboardUser(): Promise<DashboardUser | null> {
  const supabase = await createClient();
  const { data: auth } = await supabase.auth.getUser();
  if (!auth.user) return null;

  const { data } = await supabase
    .from("users")
    .select("id, name")
    .eq("id", auth.user.id)
    .maybeSingle();
  return data;
}

// For dashboard layouts and pages: returns the user or sends them to /login.
export async function requireDashboardUser(): Promise<DashboardUser> {
  const user = await findDashboardUser();
  if (!user) redirect("/login");
  return user;
}

export type SignInResult = { ok: true } | { ok: false; error: string };

export async function signIn(
  email: string,
  password: string,
): Promise<SignInResult> {
  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) return { ok: false, error: "That email and password don't match. Please try again." };

  // A valid account that isn't a dashboard user (e.g. no users row yet).
  if (!(await findDashboardUser())) {
    await supabase.auth.signOut();
    return { ok: false, error: "This account doesn't have access to the dashboard yet." };
  }
  return { ok: true };
}

export async function signOut() {
  const supabase = await createClient();
  await supabase.auth.signOut();
}
