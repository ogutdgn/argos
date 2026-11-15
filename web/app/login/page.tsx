import type { Metadata } from "next";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in · Argos" };

// Dashboard login. No sign-up: accounts are added by hand in Supabase
// (web/README.md, "Dashboard users").
export default function LoginPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-canvas px-4 py-12">
      <Card className="w-full max-w-[400px]">
        <CardHeader className="gap-2">
          <h1 className="text-3xl font-semibold">Argos</h1>
          <CardDescription>
            Welcome back. Sign in to see the people close to you.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <LoginForm />
        </CardContent>
      </Card>
    </main>
  );
}
