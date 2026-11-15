"use server";

import { refresh } from "next/cache";
import { isEmailConfigured, sendInvitationEmail } from "@/lib/email/invitation";
import { requireDashboardUser, type DashboardUser } from "@/lib/supabase/auth";
import {
  createInvitation,
  discardInvitation,
  getInvitation,
} from "@/lib/supabase/invitations";
import { isUuid } from "@/lib/validate";

export type InviteState = {
  ok?: boolean;
  message?: string;
  email?: string; // what was typed, kept in the field after a failure
};

// Loose on purpose: the email itself is the real check.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function siteUrl() {
  return process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/+$/, "") || null;
}

// Creates a new invitation row and emails its link. If the email can't be
// sent, the row is removed again so the list only shows links people got.
async function inviteByEmail(
  email: string,
  user: DashboardUser,
): Promise<InviteState> {
  const site = siteUrl();
  if (!isEmailConfigured() || !site) {
    return {
      ok: false,
      message:
        "Email isn't set up yet, so no invitation was sent. Once the email settings are added, please try again.",
    };
  }

  const { invitation, token } = await createInvitation(email, user.id);
  const sent = await sendInvitationEmail({
    to: email,
    inviterName: user.name,
    link: `${site}/invite/${token}`,
    expiresAt: invitation.expiresAt,
  });

  if (!sent.ok) {
    await discardInvitation(invitation.id);
    return {
      ok: false,
      message:
        "We couldn't send the email just now. Please check the address and try again in a moment.",
    };
  }

  refresh();
  return { ok: true, message: `Invitation sent to ${email}.` };
}

export async function invite(
  _prev: InviteState,
  formData: FormData,
): Promise<InviteState> {
  const user = await requireDashboardUser();
  const email = String(formData.get("email") ?? "")
    .trim()
    .toLowerCase();
  if (!EMAIL_PATTERN.test(email) || email.length > 254) {
    return { ok: false, message: "Please enter an email address.", email };
  }
  return { ...(await inviteByEmail(email, user)), email };
}

// "Send a new invitation" on an expired one: a new row and token for the
// same email. The expired row stays as it is.
export async function sendNewInvitation(
  _prev: InviteState,
  formData: FormData,
): Promise<InviteState> {
  const user = await requireDashboardUser();
  const id = String(formData.get("invitationId") ?? "");
  const expired = isUuid(id) ? await getInvitation(id) : null;
  if (!expired || expired.status !== "expired") {
    refresh();
    return { ok: false, message: "This invitation can't be sent again." };
  }
  return inviteByEmail(expired.email, user);
}
