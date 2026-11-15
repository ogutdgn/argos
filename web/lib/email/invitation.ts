import "server-only";
import { Resend } from "resend";

// The invitation email (docs/flows.md, Flow A), sent through Resend.
// Server only: RESEND_API_KEY never reaches the browser.

export type EmailResult =
  | { ok: true }
  | { ok: false; reason: "not_configured" | "send_failed" };

// Email clients can't read the site's CSS, so the email carries its own
// inline styles. These are the "Aegean" tokens from docs/design.md; keep
// them in step with web/app/globals.css.
const COLOR = {
  canvas: "#F7F5F0",
  surface: "#FFFFFF",
  border: "#E3DED5",
  ink: "#1F1D1A",
  muted: "#5C574F",
  primary: "#1E4D5C",
  onPrimary: "#FFFFFF",
};
const SERIF = "'Source Serif 4', Georgia, 'Times New Roman', serif";
const SANS = "'Source Sans 3', 'Helvetica Neue', Arial, sans-serif";

// True when the Resend key and sender are set. Checked before an invitation
// is created, so a missing key gives a calm message instead of a crash.
export function isEmailConfigured() {
  return Boolean(process.env.RESEND_API_KEY && process.env.RESEND_FROM_EMAIL);
}

function escapeHtml(text: string) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

type InvitationEmail = {
  to: string;
  inviterName: string;
  link: string;
  expiresAt: string;
};

function content({ inviterName, expiresAt }: InvitationEmail) {
  const until = formatDate(expiresAt);
  return {
    subject: `${inviterName} invited you to Argos`,
    paragraphs: [
      `${inviterName} has invited you to Argos.`,
      "Argos is a quiet companion for someone in your family who lives with dementia. When you visit, it recognizes your voice and softly tells them, in their ear, who you are and one thing you could talk about. That way the conversation feels easy for both of you.",
      "To take part, tell Argos a little about yourself: your name, how you are related, a few memories and recent news, a photo, and a short recording of you reading a few sentences aloud. It takes about ten minutes.",
    ],
    button: "Add yourself to Argos",
    note: `This link is just for you and works once. It is valid for one week, until ${until}. If it runs out, ask your family to send you a new one.`,
    ignore: "If you weren't expecting this email, you can safely ignore it.",
  };
}

function renderText(email: InvitationEmail) {
  const c = content(email);
  return [
    "Hello,",
    ...c.paragraphs,
    `${c.button}: ${email.link}`,
    c.note,
    c.ignore,
  ].join("\n\n");
}

function renderHtml(email: InvitationEmail) {
  const c = content(email);
  const link = escapeHtml(email.link);
  const p = (text: string) =>
    `<p style="margin:0 0 16px;font-family:${SANS};font-size:16px;line-height:1.6;color:${COLOR.ink};">${escapeHtml(text)}</p>`;

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(c.subject)}</title>
</head>
<body style="margin:0;padding:0;background:${COLOR.canvas};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:${COLOR.canvas};">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:${COLOR.surface};border:1px solid ${COLOR.border};border-radius:10px;">
<tr><td style="padding:32px;">
<p style="margin:0 0 24px;font-family:${SERIF};font-size:28px;font-weight:600;color:${COLOR.ink};">Argos</p>
${p("Hello,")}
${c.paragraphs.map(p).join("\n")}
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 24px;">
<tr><td style="border-radius:8px;background:${COLOR.primary};">
<a href="${link}" style="display:inline-block;padding:12px 20px;font-family:${SANS};font-size:16px;font-weight:600;color:${COLOR.onPrimary};text-decoration:none;border-radius:8px;">${escapeHtml(c.button)}</a>
</td></tr>
</table>
<p style="margin:0 0 16px;font-family:${SANS};font-size:14px;line-height:1.6;color:${COLOR.muted};">${escapeHtml(c.note)}</p>
<p style="margin:0 0 16px;font-family:${SANS};font-size:14px;line-height:1.6;color:${COLOR.muted};">If the button doesn't work, copy this link into your browser:<br><a href="${link}" style="color:${COLOR.primary};word-break:break-all;">${link}</a></p>
<p style="margin:0;font-family:${SANS};font-size:14px;line-height:1.6;color:${COLOR.muted};">${escapeHtml(c.ignore)}</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>`;
}

export async function sendInvitationEmail(
  email: InvitationEmail,
): Promise<EmailResult> {
  const apiKey = process.env.RESEND_API_KEY;
  const from = process.env.RESEND_FROM_EMAIL;
  if (!apiKey || !from) return { ok: false, reason: "not_configured" };

  try {
    const { error } = await new Resend(apiKey).emails.send({
      from,
      to: email.to,
      subject: content(email).subject,
      html: renderHtml(email),
      text: renderText(email),
    });
    if (error) {
      console.error("Resend refused the invitation email:", error.message);
      return { ok: false, reason: "send_failed" };
    }
    return { ok: true };
  } catch (err) {
    console.error("Could not reach Resend:", err);
    return { ok: false, reason: "send_failed" };
  }
}
