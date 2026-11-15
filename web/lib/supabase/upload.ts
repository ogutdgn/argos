import { createClient } from "./client";

// Browser side of an upload: sends a file to the signed upload URL that the
// server made with createUploadTarget() (web/lib/supabase/storage.ts).
// The token allows exactly one upload to exactly that path.
export async function uploadToTarget(
  target: { bucket: string; path: string; token: string },
  file: Blob,
  contentType: string,
): Promise<{ ok: true } | { ok: false }> {
  const supabase = createClient();
  const { error } = await supabase.storage
    .from(target.bucket)
    .uploadToSignedUrl(target.path, target.token, file, { contentType });
  return error ? { ok: false } : { ok: true };
}
