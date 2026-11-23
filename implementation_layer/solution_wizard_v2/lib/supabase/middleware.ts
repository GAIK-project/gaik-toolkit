import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { isPublicPage } from "@/lib/public-pages";
import { hasWizardAccess, supabaseSettings } from "@/lib/supabase-auth";

type CookieToSet = { name: string; value: string; options: CookieOptions };

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const settings = supabaseSettings();
  const path = request.nextUrl.pathname;
  if (!settings) {
    // Not configured: nothing but the public pages, rather than an opaque
    // @supabase/ssr crash or an open door.
    if (isPublicPage(path)) return NextResponse.next({ request });
    if (path.startsWith("/api/")) return new NextResponse("Sign-in required", { status: 401 });
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "?error=unavailable";
    return NextResponse.redirect(url);
  }
  const { url, key } = settings;

  const supabase = createServerClient(
    url,
    key,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet: CookieToSet[]) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value),
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  // Refreshes the session token. Do not add code between the getUser call and
  // returning the response, or the session may break intermittently.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Every route but the public pages needs a confirmed account with access to
  // the wizard (lib/supabase-auth). An API call without one gets 401, not a
  // page; a signed-in account still waiting for approval is told so.
  if (isPublicPage(path)) return supabaseResponse;
  if (user && (await hasWizardAccess(supabase, user))) return supabaseResponse;
  if (path.startsWith("/api/")) return new NextResponse("Sign-in required", { status: 401 });
  const login = request.nextUrl.clone();
  login.pathname = "/login";
  login.search = user ? "?error=pending" : "";
  const redirect = NextResponse.redirect(login);
  // The refreshed session cookies go with the redirect.
  supabaseResponse.cookies.getAll().forEach((cookie) => redirect.cookies.set(cookie));
  return redirect;
}
