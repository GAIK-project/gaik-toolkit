import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

// All demo routes require login + approval. The Solution Wizard is intentionally
// NOT here — it has its own finer gate in proxy.ts (login + wizard_access / team
// key), which also admits still-pending users who hold a grant.
// IMPORTANT: when adding a new page under app/(demos)/, add its route here.
const PROTECTED_ROUTES = [
  "/audio-structured",
  "/classifier",
  "/dental-transcription",
  "/diary",
  "/document-structured",
  "/extractor",
  "/incident-report",
  "/llm-judge",
  "/luvata-order",
  "/parser",
  "/postgres-agent",
  "/rag",
  "/report-writer",
  "/text-to-speech",
  "/transcriber",
  "/video-search",
  "/vision-extractor",
];

// Default route for authenticated users
const DEFAULT_DEMO_ROUTE = "/";

// Auth routes that should redirect logged-in users
const AUTH_ROUTES = ["/sign-in", "/sign-up"];

const BYPASS_AUTH = process.env.BYPASS_AUTH === "true";

function isProtectedRoute(pathname: string): boolean {
  return PROTECTED_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  );
}

function isAuthRoute(pathname: string): boolean {
  return AUTH_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  );
}

export interface AccessState {
  loggedIn: boolean;
  approved: boolean;
  wizardAccess: boolean;
}

/**
 * Read the requesting user's access state in one shot: logged in, approved
 * (general `status`), and Solution Wizard beta grant (`wizard_access`). Used by
 * the proxy's API auth gate and the wizard gate. Independent of the team `?key=`
 * shortcut. `BYPASS_AUTH` opens everything in dev.
 */
export async function getAccessState(
  request: NextRequest,
): Promise<AccessState> {
  if (BYPASS_AUTH) return { loggedIn: true, approved: true, wizardAccess: true };

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!supabaseUrl || !supabaseKey)
    return { loggedIn: false, approved: false, wizardAccess: false };

  const supabase = createServerClient(supabaseUrl, supabaseKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll() {
        // Read-only: token refresh is handled by updateSession on page routes.
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { loggedIn: false, approved: false, wizardAccess: false };

  const { data } = await supabase
    .from("access_requests")
    .select("status, wizard_access")
    .eq("user_id", user.id)
    .single();

  return {
    loggedIn: true,
    approved: data?.status === "approved",
    wizardAccess: data?.wizard_access === true,
  };
}

export async function updateSession(request: NextRequest) {
  const supabaseResponse = NextResponse.next({ request });
  const pathname = request.nextUrl.pathname;

  // Skip Supabase entirely in development mode
  if (BYPASS_AUTH) {
    return supabaseResponse;
  }

  // Supabase required for production auth
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

  if (!supabaseUrl || !supabaseKey) {
    console.warn("Supabase not configured - allowing access");
    return supabaseResponse;
  }

  let response = supabaseResponse;
  const supabase = createServerClient(supabaseUrl, supabaseKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) =>
          request.cookies.set(name, value),
        );
        response = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options),
        );
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Handle protected demo routes
  if (isProtectedRoute(pathname)) {
    if (!user) {
      const url = request.nextUrl.clone();
      url.pathname = "/sign-in";
      return NextResponse.redirect(url);
    }

    // Check access request status
    const { data: accessRequest } = await supabase
      .from("access_requests")
      .select("status")
      .eq("user_id", user.id)
      .single();

    if (!accessRequest || accessRequest.status === "pending") {
      const url = request.nextUrl.clone();
      url.pathname = "/access-pending";
      return NextResponse.redirect(url);
    }

    if (accessRequest.status === "rejected") {
      const url = request.nextUrl.clone();
      url.pathname = "/sign-in";
      return NextResponse.redirect(url);
    }
  }

  // Redirect logged-in users with approved access away from auth routes
  if (isAuthRoute(pathname) && user) {
    const { data: accessRequest } = await supabase
      .from("access_requests")
      .select("status")
      .eq("user_id", user.id)
      .single();

    if (accessRequest?.status === "approved") {
      const url = request.nextUrl.clone();
      url.pathname = DEFAULT_DEMO_ROUTE;
      return NextResponse.redirect(url);
    }

    if (accessRequest?.status === "pending") {
      const url = request.nextUrl.clone();
      url.pathname = "/access-pending";
      return NextResponse.redirect(url);
    }
  }

  return response;
}
