import type { Metadata } from "next";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in · Argos" };

// Dashboard login. No sign-up: accounts are added by hand in Supabase
// (web/README.md, "Dashboard users").
export default function LoginPage() {
  return (
    <main>
      <h1>Argos</h1>
      <p>Sign in to the dashboard.</p>
      <LoginForm />
    </main>
  );
}
