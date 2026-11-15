import "server-only";
import { createClient } from "@supabase/supabase-js";
import { supabaseEnv } from "./env";

// Supabase client with the secret key, for server code that runs without a
// dashboard login (the magic-link pages, conversation processing). It
// bypasses RLS, so use it only for the exact rows the caller may touch, and
// never import it from a Client Component ("server-only" makes that a build
// error). Prefer createClient() from ./server whenever a dashboard user is
// signed in, so RLS still applies.
export function createAdminClient() {
  const { url } = supabaseEnv();
  const secretKey = process.env.SUPABASE_SECRET_KEY;
  if (!secretKey) throw new Error("Missing SUPABASE_SECRET_KEY");

  return createClient(url, secretKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
