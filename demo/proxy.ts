import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const API_USERNAME = process.env.API_USERNAME || "";
const API_PASSWORD = process.env.API_PASSWORD || "";

export const config = {
  matcher: "/api/:path*",
};

function buildAuthHeader(): string | null {
  if (!API_USERNAME || !API_PASSWORD) return null;
  const credentials = Buffer.from(`${API_USERNAME}:${API_PASSWORD}`).toString(
    "base64",
  );
  return `Basic ${credentials}`;
}

function hasBody(method: string): boolean {
  return method !== "GET" && method !== "HEAD";
}

export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const backendPath = pathname.replace(/^\/api/, "");
  const targetUrl = `${BACKEND_URL}${backendPath}${search}`;

  const headers = new Headers();
  const auth = buildAuthHeader();
  if (auth) headers.set("Authorization", auth);

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
