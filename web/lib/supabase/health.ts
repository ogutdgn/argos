import { createClient } from "./server";

export type SupabaseHealth =
  | { ok: true; buckets: number }
  | { ok: false; reason: string };

// Minimal read that needs no tables: list the storage buckets this key can see.
// A wrong URL or key returns an error; a working connection returns a list
// (possibly empty, since buckets are private to the publishable key).
export async function checkSupabase(): Promise<SupabaseHealth> {
  try {
    const supabase = await createClient();
    const { data, error } = await supabase.storage.listBuckets();
    if (error) return { ok: false, reason: error.message };
    return { ok: true, buckets: data.length };
  } catch (e) {
    return { ok: false, reason: e instanceof Error ? e.message : "Unknown error" };
  }
}
