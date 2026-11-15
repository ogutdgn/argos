import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/proxy";

// Every page is for signed-in dashboard users unless it is listed here.
// New dashboard pages are protected without any change to this file.
const PUBLIC_PATHS = [
  "/login",
  "/invite", // magic-link form for invited people (no account)
  "/plan", // live task plan
  "/api", // endpoints check their own auth (e.g. the station's secret)
];

function isPublic(pathname: string) {
  return PUBLIC_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );
}

export async function proxy(request: NextRequest) {
  const { response, signedIn } = await updateSession(request);

  if (signedIn || isPublic(request.nextUrl.pathname)) {
    return response;
  }

  // Optimistic check only. The dashboard layout checks again, including
  // that the account has a row in the users table.
  const redirect = NextResponse.redirect(new URL("/login", request.url));
  response.cookies.getAll().forEach((cookie) => redirect.cookies.set(cookie));
  return redirect;
}

export const config = {
  matcher: [
    // Skip Next.js internals and static files.
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
