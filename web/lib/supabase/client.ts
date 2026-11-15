import { createBrowserClient } from "@supabase/ssr";
import { supabaseEnv } from "./env";

// Supabase client for Client Components (code that runs in the browser).
export function createClient() {
  const { url, publishableKey } = supabaseEnv();
  return createBrowserClient(url, publishableKey);
}
