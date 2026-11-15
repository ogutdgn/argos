import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { supabaseEnv } from "./env";

// Used only by web/proxy.ts. Refreshes the login session on every request
// (Server Components can't write cookies, so the refresh has to happen here)
// and says whether the request carries a valid session.
export async function updateSession(request: NextRequest) {
  const { url, publishableKey } = supabaseEnv();
  let response = NextResponse.next({ request });

  const supabase = createServerClient(url, publishableKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet, headers) {
        cookiesToSet.forEach(({ name, value }) =>
          request.cookies.set(name, value),
        );
        response = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options),
        );
        Object.entries(headers ?? {}).forEach(([key, value]) =>
          response.headers.set(key, value),
        );
      },
    },
  });

  // Verifies the token (and refreshes it if needed). Don't put code between
  // creating the client and this call.
  const { data } = await supabase.auth.getClaims();

  return { response, signedIn: Boolean(data?.claims) };
}
