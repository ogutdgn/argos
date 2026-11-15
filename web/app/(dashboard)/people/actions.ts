"use server";

import { randomUUID } from "node:crypto";
import { refresh } from "next/cache";
import { requireDashboardUser } from "@/lib/supabase/auth";
import { deleteMemoryItem, updateMemoryItem } from "@/lib/supabase/memory";
import { createPatient, getPatient, isUuid } from "@/lib/supabase/people";
import {
  createUploadTarget,
  isPhotoType,
  isUploaded,
  PHOTO_TYPES,
  type UploadTarget,
} from "@/lib/supabase/storage";

// Every action checks the dashboard user itself: Server Actions can be called
// with a direct POST, not only from our pages.

type Result = { ok: true } | { ok: false; error: string };

const SAVE_ERROR = "That didn't save. Please try again in a moment.";
const MAX_CONTENT = 2000;

function isDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().startsWith(value);
}

// Memory items ------------------------------------------------------------

export async function saveMemoryItem(input: {
  id: string;
  content: string;
  occurredOn: string;
}): Promise<Result> {
  await requireDashboardUser();
  const content = typeof input.content === "string" ? input.content.trim() : "";
  if (!isUuid(input.id)) return { ok: false, error: SAVE_ERROR };
  if (!content) return { ok: false, error: "Please write a few words before saving." };
  if (content.length > MAX_CONTENT) {
    return { ok: false, error: "That is a little long. Please keep it shorter." };
  }
  if (!isDate(input.occurredOn)) return { ok: false, error: "Please pick a date." };

  try {
    const personId = await updateMemoryItem(input.id, {
      content,
      occurredOn: input.occurredOn,
    });
    if (!personId) return { ok: false, error: SAVE_ERROR };
  } catch {
    return { ok: false, error: SAVE_ERROR };
  }
  refresh();
  return { ok: true };
}

export async function removeMemoryItem(id: string): Promise<Result> {
  await requireDashboardUser();
  if (!isUuid(id)) return { ok: false, error: SAVE_ERROR };
  try {
    await deleteMemoryItem(id);
  } catch {
    return { ok: false, error: "That didn't delete. Please try again in a moment." };
  }
  refresh();
  return { ok: true };
}

// Adding the patient ------------------------------------------------------
// 1. preparePatientUploads: picks the new person's id and returns one-time
//    upload targets under it (voice sample, optional photo).
// 2. The browser uploads the files straight to storage.
// 3. addPatient: checks the files are there and inserts the row.
// The row is only created once the voice sample is stored, so there is never
// a patient without a voice.

export type PatientUploads =
  | { ok: true; personId: string; voice: UploadTarget; photo: UploadTarget | null }
  | { ok: false; error: string };

const PATIENT_EXISTS = "The patient is already added.";

export async function preparePatientUploads(input: {
  photoType: string | null;
}): Promise<PatientUploads> {
  await requireDashboardUser();
  if (input.photoType !== null && !isPhotoType(input.photoType)) {
    return { ok: false, error: "Please choose a JPEG, PNG or WebP photo." };
  }

  try {
    if (await getPatient()) return { ok: false, error: PATIENT_EXISTS };
    const personId = randomUUID();
    const [voice, photo] = await Promise.all([
      createUploadTarget("voice-samples", personId, "wav"),
      input.photoType
        ? createUploadTarget("photos", personId, PHOTO_TYPES[input.photoType])
        : Promise.resolve(null),
    ]);
    return { ok: true, personId, voice, photo };
  } catch {
    return { ok: false, error: SAVE_ERROR };
  }
}

export async function addPatient(input: {
  personId: string;
  name: string;
  voiceSamplePath: string;
  photoPath: string | null;
}): Promise<Result> {
  await requireDashboardUser();
  const name = typeof input.name === "string" ? input.name.trim() : "";
  if (!name) return { ok: false, error: "Please add the patient's name." };
  if (name.length > 100) return { ok: false, error: "Please use a shorter name." };
  if (!isUuid(input.personId)) return { ok: false, error: SAVE_ERROR };

  try {
    const [voiceOk, photoOk] = await Promise.all([
      isUploaded("voice-samples", input.personId, input.voiceSamplePath),
      input.photoPath === null
        ? Promise.resolve(true)
        : isUploaded("photos", input.personId, input.photoPath),
    ]);
    if (!voiceOk || !photoOk) return { ok: false, error: SAVE_ERROR };

    const created = await createPatient({
      id: input.personId,
      name,
      photoPath: input.photoPath,
      voiceSamplePath: input.voiceSamplePath,
    });
    if (!created.ok) {
      return {
        ok: false,
        error: created.reason === "patient_exists" ? PATIENT_EXISTS : SAVE_ERROR,
      };
    }
  } catch {
    return { ok: false, error: SAVE_ERROR };
  }
  return { ok: true };
}
