import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

// Protected demo routes that require approved access
const PROTECTED_ROUTES = [
  "/classifier",
  "/extractor",
  "/incident-report",
  "/parser",
  "/rag",
  "/transcriber",
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
