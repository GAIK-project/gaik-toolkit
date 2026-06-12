import { ratelimit } from "@/lib/rate-limit";
import { updateSession } from "@/lib/supabase/proxy";
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

  // Solution Wizard is gated behind a shared secret while it is "coming
  // soon". Default-deny: with no WIZARD_ACCESS_SECRET set, the wizard is
  // fully closed. Team access: /solution-wizard?key=<secret> sets a cookie.
  if (
    pathname.startsWith("/solution-wizard") ||
    pathname.startsWith("/api/wizard")
  ) {
    const secret = process.env.WIZARD_ACCESS_SECRET;
    const cookieKey = request.cookies.get("wizard_access")?.value;
    const queryKey = request.nextUrl.searchParams.get("key");
    const allowed = !!secret && (cookieKey === secret || queryKey === secret);

    if (!allowed) {
      if (pathname.startsWith("/api/wizard")) {
        return NextResponse.json(
          { error: "Solution Wizard is not publicly available yet." },
          { status: 403 },
        );
      }
      return NextResponse.redirect(new URL("/", request.url));
    }

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
  }

  // Proxy API requests to backend (except Next.js API routes)
  const isNextApiRoute =
    pathname.startsWith("/api/auth") || pathname.startsWith("/api/admin");
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
