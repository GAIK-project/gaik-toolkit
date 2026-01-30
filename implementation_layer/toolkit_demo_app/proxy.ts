import { NextRequest, NextResponse } from "next/server";
import { updateSession } from "@/lib/supabase/proxy";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|logos/).*)"],
};

function hasBody(method: string): boolean {
  return method !== "GET" && method !== "HEAD";
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Proxy API requests to backend
  if (pathname.startsWith("/api") && !pathname.startsWith("/api/auth")) {
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
