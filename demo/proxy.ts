import { NextRequest, NextResponse } from "next/server";

// Backend API URL (server-side only, NOT exposed to browser)
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const API_USERNAME = process.env.API_USERNAME || "";
const API_PASSWORD = process.env.API_PASSWORD || "";

export const config = {
  // Match all /api/* routes
  matcher: "/api/:path*",
};

export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  // Strip /api prefix to get the actual backend path
  // /api/parse/ -> /parse/
  const backendPath = pathname.replace(/^\/api/, "");
  const targetUrl = new URL(backendPath + search, BACKEND_URL);

  // Clone request headers and add Basic Auth
  const requestHeaders = new Headers(request.headers);

  // Add Basic Auth header if credentials are configured
  if (API_USERNAME && API_PASSWORD) {
    const credentials = Buffer.from(`${API_USERNAME}:${API_PASSWORD}`).toString(
      "base64"
    );
    requestHeaders.set("Authorization", `Basic ${credentials}`);
  }

  // Remove headers that shouldn't be forwarded
  requestHeaders.delete("host");

  // Rewrite request to backend URL
  return NextResponse.rewrite(targetUrl, {
    request: {
      headers: requestHeaders,
    },
  });
}
