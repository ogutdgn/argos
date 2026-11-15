import { Suspense } from "react";
import { connection } from "next/server";
import { checkSupabase } from "@/lib/supabase/health";

// Empty start page. Its only job for now is to prove the app can read from
// Supabase; the dashboard (W1.x) replaces it.
async function SupabaseStatus() {
  await connection();
  const health = await checkSupabase();

  if (!health.ok) {
    return <p>Supabase: not connected ({health.reason})</p>;
  }
  return <p>Supabase: connected ({health.buckets} visible storage buckets)</p>;
}

export default function Home() {
  return (
    <main>
      <h1>Argos</h1>
      <Suspense fallback={<p>Supabase: checking…</p>}>
        <SupabaseStatus />
      </Suspense>
    </main>
  );
}
