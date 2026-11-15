import "server-only";
import { createHash, randomBytes } from "node:crypto";
import { createAdminClient } from "./admin";
import { createClient } from "./server";

// Invitations: a one-time magic link per invited person (docs/flows.md,
// Flow A). Table: public.invitations (supabase/migrations, docs/structure.md
// "The contract"). Only the SHA-256 hash of the link token is stored; the raw
// token exists only in the emailed link.
//
// Dashboard functions use the signed-in user's client, so RLS applies.
// Link functions (getValidInvitation, markInvitationUsed) run for people who
// are not signed in, so they use the secret key and only touch the one row
// whose token was presented.

export type InvitationStatus = "pending" | "used" | "expired";

export type Invitation = {
  id: string;
  email: string;
  createdAt: string;
  expiresAt: string;
  usedAt: string | null;
  personId: string | null;
  status: InvitationStatus;
};

type InvitationRow = {
  id: string;
  email: string;
  created_at: string;
  expires_at: string;
  used_at: string | null;
  person_id: string | null;
};

const COLUMNS = "id, email, created_at, expires_at, used_at, person_id";

// 32 random bytes, base64url: 43 characters, safe in a URL path.
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{43}$/;

function newToken() {
  return randomBytes(32).toString("base64url");
}

function hashToken(token: string) {
  return createHash("sha256").update(token).digest("hex");
}

function statusOf(row: InvitationRow, now: Date): InvitationStatus {
  if (row.used_at) return "used";
  return new Date(row.expires_at) <= now ? "expired" : "pending";
}

function toInvitation(row: InvitationRow, now: Date): Invitation {
  return {
    id: row.id,
    email: row.email,
    createdAt: row.created_at,
    expiresAt: row.expires_at,
    usedAt: row.used_at,
    personId: row.person_id,
    status: statusOf(row, now),
  };
}

// --- Dashboard ------------------------------------------------------------

// Every invitation, newest first.
export async function listInvitations(): Promise<Invitation[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("invitations")
    .select(COLUMNS)
    .order("created_at", { ascending: false });
  if (error) throw new Error(`Could not load invitations: ${error.message}`);

  const now = new Date();
  return (data as InvitationRow[]).map((row) => toInvitation(row, now));
}

export async function getInvitation(id: string): Promise<Invitation | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("invitations")
    .select(COLUMNS)
    .eq("id", id)
    .maybeSingle();
  if (error) throw new Error(`Could not load the invitation: ${error.message}`);
  return data ? toInvitation(data as InvitationRow, new Date()) : null;
}

// A new invitation row with a fresh token. The returned token goes into the
// email link and nowhere else. expires_at comes from the table default
// (+7 days). Sending a new invitation after one expired is just another call:
// the old row stays as it is.
export async function createInvitation(
  email: string,
  invitedBy: string,
): Promise<{ invitation: Invitation; token: string }> {
  const token = newToken();
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("invitations")
    .insert({ email, token_hash: hashToken(token), invited_by: invitedBy })
    .select(COLUMNS)
    .single();
  if (error) throw new Error(`Could not create the invitation: ${error.message}`);

  return { invitation: toInvitation(data as InvitationRow, new Date()), token };
}

// Removes an invitation whose email could not be sent, so the list never
// shows a link nobody received.
export async function discardInvitation(id: string): Promise<void> {
  const supabase = await createClient();
  const { error } = await supabase.from("invitations").delete().eq("id", id);
  if (error) throw new Error(`Could not remove the invitation: ${error.message}`);
}

// --- Magic link (no login) ------------------------------------------------

export type ValidInvitation = { id: string; email: string; expiresAt: string };

// The invitation behind a link token, or null when the token is unknown,
// already used or expired. Opening the link does not use it up (email
// scanners open links too); the form submit does, with markInvitationUsed.
export async function getValidInvitation(
  token: string,
): Promise<ValidInvitation | null> {
  if (!TOKEN_PATTERN.test(token)) return null;

  const supabase = createAdminClient();
  const { data, error } = await supabase
    .from("invitations")
    .select(COLUMNS)
    .eq("token_hash", hashToken(token))
    .maybeSingle();
  if (error) throw new Error(`Could not check the invitation: ${error.message}`);
  if (!data) return null;

  const row = data as InvitationRow;
  if (statusOf(row, new Date()) !== "pending") return null;
  return { id: row.id, email: row.email, expiresAt: row.expires_at };
}

// Uses up the link: sets used_at and person_id in one UPDATE that only
// matches while used_at is null and the link hasn't expired, so two submits
// at once can't both win. Returns false when the link was already used or
// has expired; the caller (the W1.4 form) should then undo what it created
// for that submit and show the refusal.
export async function markInvitationUsed(
  invitationId: string,
  personId: string,
): Promise<boolean> {
  const now = new Date().toISOString();
  const supabase = createAdminClient();
  const { data, error } = await supabase
    .from("invitations")
    .update({ used_at: now, person_id: personId })
    .eq("id", invitationId)
    .is("used_at", null)
    .gt("expires_at", now)
    .select("id");
  if (error) throw new Error(`Could not use the invitation: ${error.message}`);
  return data.length === 1;
}
