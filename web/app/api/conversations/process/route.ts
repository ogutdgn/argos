import { createHash, timingSafeEqual } from "node:crypto";
import { after, NextResponse } from "next/server";
import { processConversation } from "@/lib/processing/process";
import { claimConversation, getConversationStatus } from "@/lib/supabase/processing";
import { isUuid } from "@/lib/validate";

// The station calls this after uploading a conversation (docs/structure.md,
// "Station → web handoff"). It answers at once; the work runs in after():
// transcription, memory, new reminders. /api is public in proxy.ts, so this
// route checks the station's secret itself.

// Transcribing a long visit, reading it and making reminders can take a
// few minutes; after() runs within this limit.
export const maxDuration = 300;

function json(status: number, body: Record<string, string>) {
  return NextResponse.json(body, { status });
}

// Constant-time comparison. Hashing first gives both sides the same length,
// so the length of the secret doesn't leak either.
function isStation(request: Request, secret: string) {
  const header = request.headers.get("authorization") ?? "";
  const given = header.startsWith("Bearer ") ? header.slice("Bearer ".length) : "";
  const a = createHash("sha256").update(given).digest();
  const b = createHash("sha256").update(secret).digest();
  return given.length > 0 && timingSafeEqual(a, b);
}

export async function POST(request: Request) {
  const secret = process.env.STATION_API_SECRET;
  if (!secret) {
    console.error("STATION_API_SECRET is not set; refusing every call");
    return json(500, { error: "internal" });
  }
  if (!isStation(request, secret)) return json(401, { error: "unauthorized" });

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json(400, { error: "invalid_request" });
  }
  const id =
    typeof body === "object" && body !== null
      ? (body as Record<string, unknown>).conversation_id
      : undefined;
  if (!isUuid(id)) return json(400, { error: "invalid_request" });

  try {
    const status = await getConversationStatus(id);
    if (status === null) return json(404, { error: "conversation_not_found" });
    if (status === "processing" || status === "processed") {
      return json(200, { conversation_id: id, status });
    }

    if (!(await claimConversation(id))) {
      // Another call claimed it a moment ago.
      const now = await getConversationStatus(id);
      return json(200, { conversation_id: id, status: now ?? "processing" });
    }
    after(() => processConversation(id));
    return json(202, { conversation_id: id, status: "processing" });
  } catch (err) {
    console.error(`Could not start processing conversation ${id}`, err);
    return json(500, { error: "internal" });
  }
}
