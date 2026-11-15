"use server";

import { after } from "next/server";
import { regenerateReminder } from "@/lib/reminders/regenerate";
import { getValidInvitation } from "@/lib/supabase/invitations";
import {
  prepareRegistrationUploads,
  registerInvitedPerson,
  registrationPersonId,
  type RegistrationInput,
} from "@/lib/supabase/registration";
import { isPhotoType, type UploadTarget } from "@/lib/supabase/storage";

// The magic-link form's actions. Nobody is signed in, and Server Actions can
// be called with a direct POST, so every action checks the link token again
// before touching anything. The person's id and folders come from the
// invitation on the server (lib/supabase/registration.ts), never from the
// browser.

const SAVE_ERROR = "That didn't send. Please try again in a moment.";

const MAX_NAME = 100;
const MAX_ITEM = 2000;
const MAX_ITEMS_PER_KIND = 20;

// "used" covers unknown, used and expired links: the page shows the same
// calm answer for all three.
export type InviteResult =
  | { ok: true }
  | { ok: false; reason: "used" }
  | { ok: false; reason: "error"; error: string };

export type InviteUploads =
  | { ok: true; voice: UploadTarget; photo: UploadTarget }
  | Exclude<InviteResult, { ok: true }>;

function text(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

// One memory item per non-empty line.
function lines(value: unknown) {
  return text(value)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

async function checkLink(token: unknown) {
  if (typeof token !== "string") return null;
  return getValidInvitation(token);
}

export async function prepareInviteUploads(input: {
  token: string;
  photoType: string;
}): Promise<InviteUploads> {
  if (!isPhotoType(input.photoType)) {
    return { ok: false, reason: "error", error: "Please choose a JPEG, PNG or WebP photo." };
  }
  try {
    const invitation = await checkLink(input.token);
    if (!invitation) return { ok: false, reason: "used" };
    const targets = await prepareRegistrationUploads(invitation, input.photoType);
    return { ok: true, ...targets };
  } catch (err) {
    console.error(err);
    return { ok: false, reason: "error", error: SAVE_ERROR };
  }
}

export async function submitInvite(input: {
  token: string;
  name: string;
  relationship: string;
  facts: string;
  sharedMemories: string;
  recentEvents: string;
  voiceSamplePath: string;
  photoPath: string;
}): Promise<InviteResult> {
  const name = text(input.name);
  const relationship = text(input.relationship);
  if (!name) return { ok: false, reason: "error", error: "Please add your name." };
  if (!relationship) {
    return { ok: false, reason: "error", error: "Please say how you are related." };
  }
  if (name.length > MAX_NAME || relationship.length > MAX_NAME) {
    return { ok: false, reason: "error", error: "Please keep your name and relationship shorter." };
  }

  const groups = [
    { kind: "fact", items: lines(input.facts) },
    { kind: "shared_memory", items: lines(input.sharedMemories) },
    { kind: "recent_event", items: lines(input.recentEvents) },
  ] as const;
  const memory: RegistrationInput["memory"] = groups.flatMap(({ kind, items }) =>
    items.map((content) => ({ kind, content })),
  );
  if (memory.length === 0) {
    return { ok: false, reason: "error", error: "Please share at least one thing about yourself." };
  }
  if (
    groups.some((g) => g.items.length > MAX_ITEMS_PER_KIND) ||
    memory.some((item) => item.content.length > MAX_ITEM)
  ) {
    return { ok: false, reason: "error", error: "That is a little long. Please keep it shorter." };
  }
  if (typeof input.voiceSamplePath !== "string" || typeof input.photoPath !== "string") {
    return { ok: false, reason: "error", error: SAVE_ERROR };
  }

  try {
    const invitation = await checkLink(input.token);
    if (!invitation) return { ok: false, reason: "used" };

    const saved = await registerInvitedPerson(invitation, {
      name,
      relationship,
      memory,
      voiceSamplePath: input.voiceSamplePath,
      photoPath: input.photoPath,
    });
    if (saved.ok) {
      // Their first reminder, made after the thank-you page is on its way.
      const personId = registrationPersonId(invitation.id);
      after(() => regenerateReminder(personId));
      return { ok: true };
    }
    if (saved.reason === "used") return { ok: false, reason: "used" };
    return { ok: false, reason: "error", error: SAVE_ERROR };
  } catch (err) {
    console.error(err);
    return { ok: false, reason: "error", error: SAVE_ERROR };
  }
}
