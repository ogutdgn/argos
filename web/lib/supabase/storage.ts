import { randomUUID } from "node:crypto";
import type { SupabaseClient } from "@supabase/supabase-js";
import { createClient } from "./server";

// Server-side storage helpers for the private buckets (docs/structure.md,
// "Storage buckets"). Files are uploaded from the browser with a one-time
// signed upload URL (web/lib/supabase/upload.ts), so large photos never pass
// through a Vercel function. Every upload gets a new path.
//
// The client defaults to the signed-in dashboard user (RLS). The magic-link
// form can pass its own server client instead.

export type Bucket = "photos" | "voice-samples";

export type UploadTarget = { bucket: Bucket; path: string; token: string };

const SIGNED_URL_SECONDS = 60 * 60; // 1 hour

export const PHOTO_TYPES = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
} as const;
export type PhotoType = keyof typeof PHOTO_TYPES;

export function isPhotoType(value: unknown): value is PhotoType {
  return typeof value === "string" && value in PHOTO_TYPES;
}

// `{person_id}/{uuid}.{ext}`
export async function createUploadTarget(
  bucket: Bucket,
  personId: string,
  ext: string,
  client?: SupabaseClient,
): Promise<UploadTarget> {
  const supabase = client ?? (await createClient());
  const path = `${personId}/${randomUUID()}.${ext}`;
  const { data, error } = await supabase.storage
    .from(bucket)
    .createSignedUploadUrl(path);
  if (error) throw error;
  return { bucket, path: data.path, token: data.token };
}

// True when the path is one createUploadTarget could have made for this
// person, and the file is really there.
export async function isUploaded(
  bucket: Bucket,
  personId: string,
  path: string,
  client?: SupabaseClient,
): Promise<boolean> {
  const pattern = new RegExp(
    `^${personId}/[0-9a-f-]{36}\\.(wav|jpg|png|webp)$`,
  );
  if (!pattern.test(path)) return false;
  const supabase = client ?? (await createClient());
  const { data } = await supabase.storage.from(bucket).exists(path);
  return Boolean(data);
}

// Signed URLs for showing private files, keyed by path. Missing files and
// null paths are left out.
export async function signedUrls(
  bucket: Bucket,
  paths: (string | null)[],
  client?: SupabaseClient,
): Promise<Map<string, string>> {
  const wanted = [...new Set(paths.filter((p): p is string => Boolean(p)))];
  const urls = new Map<string, string>();
  if (wanted.length === 0) return urls;

  const supabase = client ?? (await createClient());
  const { data } = await supabase.storage
    .from(bucket)
    .createSignedUrls(wanted, SIGNED_URL_SECONDS);
  for (const item of data ?? []) {
    if (item.path && item.signedUrl && !item.error) urls.set(item.path, item.signedUrl);
  }
  return urls;
}
