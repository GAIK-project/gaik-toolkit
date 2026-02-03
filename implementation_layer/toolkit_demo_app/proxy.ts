import { ratelimit } from "@/lib/rate-limit";
import { updateSession } from "@/lib/supabase/proxy";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|logos/).*)"],
};

function hasBody(method: string): boolean {
  return method !== "GET" && method !== "HEAD";
}

export default async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Proxy API requests to backend (except Next.js API routes)
  const isNextApiRoute =
    pathname.startsWith("/api/auth") || pathname.startsWith("/api/admin");
  if (pathname.startsWith("/api") && !isNextApiRoute) {
    // Rate limit check (if Redis is configured)
    if (ratelimit) {
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
    }

    const backendPath = pathname.replace(/^\/api/, "");
    const targetUrl = `${BACKEND_URL}${backendPath}${request.nextUrl.search}`;

    const headers = new Headers();
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);

    try {
      const response = await fetch(targetUrl, {
        method: request.method,
        headers,
        body: hasBody(request.method) ? request.body : undefined,
        // @ts-expect-error duplex required for streaming request body
        duplex: "half",
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
