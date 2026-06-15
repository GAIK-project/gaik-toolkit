import { ratelimit } from "@/lib/rate-limit";
import { getAccessState, updateSession } from "@/lib/supabase/proxy";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|logos/|data/).*)"],
};

function hasBody(method: string): boolean {
  return method !== "GET" && method !== "HEAD";
}

export default async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Solution Wizard access gate. Two independent ways in:
  //   1. Team shortcut: /solution-wizard?key=<WIZARD_ACCESS_SECRET> sets a
  //      30-day `wizard_access` cookie (works without login). Unset the secret
  //      in the environment to disable this path entirely.
  //   2. Registered beta testers: a logged-in user whose access_requests row
  //      has wizard_access = true (granted by an admin in /admin).
  // Dev: BYPASS_AUTH opens the wizard. Default-deny otherwise.
  if (
    pathname.startsWith("/solution-wizard") ||
    pathname.startsWith("/api/wizard")
  ) {
    const isApi = pathname.startsWith("/api/wizard");
    const secret = process.env.WIZARD_ACCESS_SECRET;
    const cookieKey = request.cookies.get("wizard_access")?.value;
    const queryKey = request.nextUrl.searchParams.get("key");
    const teamAllowed =
      !!secret && (cookieKey === secret || queryKey === secret);

    if (teamAllowed) {
      if (queryKey === secret && cookieKey !== secret) {
        // First visit with ?key= — set the access cookie and drop the key
        // from the URL.
        const cleanUrl = request.nextUrl.clone();
        cleanUrl.searchParams.delete("key");
        const response = NextResponse.redirect(cleanUrl);
        response.cookies.set("wizard_access", secret, {
          httpOnly: true,
          secure: true,
          sameSite: "lax",
          path: "/",
          maxAge: 60 * 60 * 24 * 30, // 30 days
        });
        return response;
      }
      // Otherwise allowed via the team key/cookie — fall through.
    } else {
      // No team key: allow registered beta testers (logged-in + wizard_access).
      const { loggedIn, wizardAccess } = await getAccessState(request);
      if (!wizardAccess) {
        if (isApi) {
          return NextResponse.json(
            { error: "Solution Wizard is not available yet." },
            { status: 403 },
          );
        }
        // Page: send anonymous visitors to sign-in (to register / request
        // access); send logged-in users without the flag back to the home page.
        return NextResponse.redirect(
          new URL(loggedIn ? "/" : "/sign-in", request.url),
        );
      }
      // Otherwise allowed via registered beta access — fall through.
    }
  }

  // Proxy API requests to backend (except Next.js API routes)
  const isNextApiRoute =
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/api/admin") ||
    pathname === "/api/report-writer/run"; // owned by its route handler
  if (pathname.startsWith("/api") && !isNextApiRoute) {
    // Rate limit only POST requests (heavy processing endpoints)
    if (ratelimit && request.method === "POST") {
      try {
        const ip =
          request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ??
          request.headers.get("x-real-ip") ??
          "anonymous";

        const { success, limit, remaining, reset } = await ratelimit.limit(ip);

        if (!success) {
          return NextResponse.json(
            { error: "Liian monta pyyntöä. Yritä hetken päästä uudelleen." },
            {
              status: 429,
              headers: {
                "X-RateLimit-Limit": limit.toString(),
                "X-RateLimit-Remaining": remaining.toString(),
                "X-RateLimit-Reset": reset.toString(),
              },
            },
          );
        }
      } catch (error) {
        console.warn(
          "[rate-limit] Redis unavailable, skipping rate limit:",
          error instanceof Error ? error.message : error,
        );
      }
    }

    // Require login + approval for heavy backend POSTs. (The wizard API is
    // already gated above, incl. the team-key path, so skip it here.)
    if (request.method === "POST" && !pathname.startsWith("/api/wizard")) {
      const { loggedIn, approved } = await getAccessState(request);
      if (!loggedIn) {
        return NextResponse.json(
          { error: "Sign in to use this feature." },
          { status: 401 },
        );
      }
      if (!approved) {
        return NextResponse.json(
          { error: "Your access is pending approval." },
          { status: 403 },
        );
      }
    }

    const backendPath = pathname.replace(/^\/api/, "");
    const targetUrl = `${BACKEND_URL}${backendPath}${request.nextUrl.search}`;

    const headers = new Headers();
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);

    try {
      // Buffer the full body to preserve binary integrity for large
      // multipart uploads. Streaming truncates data in Bun/standalone.
      let body: ArrayBuffer | null = null;
      if (hasBody(request.method)) {
        body = await request.arrayBuffer();
        headers.set("content-length", body.byteLength.toString());
      }

      const response = await fetch(targetUrl, {
        method: request.method,
        headers,
        body,
      });

      // For SSE streaming responses, pass through directly
      if (response.headers.get("content-type")?.includes("text/event-stream")) {
        return new Response(response.body, {
          status: response.status,
          statusText: response.statusText,
          headers: {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
          },
        });
      }

      return new NextResponse(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: new Headers(response.headers),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Proxy error";
      return NextResponse.json({ error: message }, { status: 502 });
    }
  }

  // Handle Supabase session for all non-API routes
  const response = await updateSession(request);
  response.headers.set("x-current-path", pathname);
  return response;
}
