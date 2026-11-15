import "server-only";
import { createHash } from "node:crypto";
import { createAdminClient } from "./admin";
import { markInvitationUsed, type ValidInvitation } from "./invitations";
import type { MemoryKind } from "@/lib/memory";
import {
  createUploadTarget,
  isUploaded,
  PHOTO_TYPES,
  type Bucket,
  type PhotoType,
  type UploadTarget,
} from "./storage";

// Registration through the magic link (docs/flows.md, Flow A). The invited
// person is not signed in, so everything here uses the secret-key client.
// Callers pass an invitation they have just checked with getValidInvitation()
// in the same server action; nothing here trusts an id sent by the browser.
//
// The person's id comes from the invitation id (registrationPersonId), never
// from the browser. That gives three things without changing the contract:
// - uploads can only land under that invitation's own folder,
// - the server can check a path belongs to the invitation by its prefix,
// - a second submit (double click, two tabs) can't create a second person:
//   it hits the people primary key and is refused.

// One stable person id per invitation: a version 8 (custom) UUID from
// SHA-256 of the invitation id (RFC 9562).
export function registrationPersonId(invitationId: string): string {
  const bytes = createHash("sha256")
    .update(`argos-registration:${invitationId}`)
    .digest()
    .subarray(0, 16);
  bytes[6] = (bytes[6] & 0x0f) | 0x80; // version 8
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // RFC 9562 variant
  const hex = bytes.toString("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export async function prepareRegistrationUploads(
  invitation: ValidInvitation,
  photoType: PhotoType,
): Promise<{ voice: UploadTarget; photo: UploadTarget }> {
  const personId = registrationPersonId(invitation.id);
  const supabase = createAdminClient();
  const [voice, photo] = await Promise.all([
    createUploadTarget("voice-samples", personId, "wav", supabase),
    createUploadTarget("photos", personId, PHOTO_TYPES[photoType], supabase),
  ]);
  return { voice, photo };
}

export type RegistrationInput = {
  name: string;
  relationship: string;
  memory: { kind: Exclude<MemoryKind, "follow_up">; content: string }[];
  voiceSamplePath: string;
  photoPath: string;
};

export type RegistrationResult =
  | { ok: true }
  // The link was used (or ran out) while this submit was on its way.
  | { ok: false; reason: "used" }
  // The files aren't where they should be: upload again.
  | { ok: false; reason: "missing_files" }
  | { ok: false; reason: "error" };

// Saves the person, then their memory items, then uses up the link.
//
// Order, without transactions (supabase-js has none):
// 1. Insert the person under the invitation's own id. A second submit for the
//    same link fails here on the primary key and changes nothing.
// 2. Insert their memory items. If that fails, delete the person (memory
//    items cascade) so the link can simply be tried again.
// 3. Use up the link (markInvitationUsed: one conditional UPDATE). Only now
//    does the link stop working. If it was already used or expired, delete
//    the person again.
// 4. Best effort: remove files left in the person's folders by earlier tries.
//
// The link is never used up for a person who isn't fully saved, so a failure
// before step 3 never locks the family member out. The one leftover case is
// the server stopping between steps 1 and 3: a person row without a used
// link. A later submit for that link is then refused at step 1, and a
// dashboard user can send a new invitation.
export async function registerInvitedPerson(
  invitation: ValidInvitation,
  input: RegistrationInput,
): Promise<RegistrationResult> {
  const personId = registrationPersonId(invitation.id);
  const supabase = createAdminClient();

  const [voiceOk, photoOk] = await Promise.all([
    isUploaded("voice-samples", personId, input.voiceSamplePath, supabase),
    isUploaded("photos", personId, input.photoPath, supabase),
  ]);
  if (!voiceOk || !photoOk) return { ok: false, reason: "missing_files" };

  // 1. The person.
  const { error: personError } = await supabase.from("people").insert({
    id: personId,
    name: input.name,
    relationship: input.relationship,
    is_patient: false,
    photo_path: input.photoPath,
    voice_sample_path: input.voiceSamplePath,
  });
  if (personError) {
    // 23505: this link's person already exists (another submit got there).
    if (personError.code === "23505") return { ok: false, reason: "used" };
    console.error("Could not save the invited person", personError);
    return { ok: false, reason: "error" };
  }

  const undo = async () => {
    const { error } = await supabase.from("people").delete().eq("id", personId);
    if (error) console.error("Could not remove the unfinished person", error);
  };

  // 2. Their memory items: first-hand, from registration, so
  // told_by_person_id and source_conversation_id stay null. occurred_on is
  // left to its default (today): when they told us.
  if (input.memory.length > 0) {
    const { error } = await supabase.from("memory_items").insert(
      input.memory.map((item) => ({
        person_id: personId,
        kind: item.kind,
        content: item.content,
      })),
    );
    if (error) {
      console.error("Could not save the invited person's memory", error);
      await undo();
      return { ok: false, reason: "error" };
    }
  }

  // 3. Use up the link.
  let used: boolean;
  try {
    used = await markInvitationUsed(invitation.id, personId);
  } catch (err) {
    console.error(err);
    await undo();
    return { ok: false, reason: "error" };
  }
  if (!used) {
    await undo();
    return { ok: false, reason: "used" };
  }

  // 4. Tidy up. The link is used now, so no other submit can still need
  // these files.
  await Promise.all([
    removeOtherFiles("voice-samples", personId, input.voiceSamplePath),
    removeOtherFiles("photos", personId, input.photoPath),
  ]);
  return { ok: true };
}

// Removes every file in the person's folder except the one that was saved:
// uploads from an earlier try or from another tab. Errors are only logged.
async function removeOtherFiles(bucket: Bucket, personId: string, keep: string) {
  const supabase = createAdminClient();
  const { data, error } = await supabase.storage.from(bucket).list(personId);
  if (error) {
    console.error(`Could not list ${bucket}/${personId}`, error);
    return;
  }
  const extra = data
    .map((file) => `${personId}/${file.name}`)
    .filter((path) => path !== keep);
  if (extra.length === 0) return;
  const { error: removeError } = await supabase.storage.from(bucket).remove(extra);
  if (removeError) console.error(`Could not tidy ${bucket}/${personId}`, removeError);
}
