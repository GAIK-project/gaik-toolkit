import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const API_USERNAME = process.env.API_USERNAME || "";
const API_PASSWORD = process.env.API_PASSWORD || "";
const AUTH_REALM = "GAIK Demo";

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

/**
 * Verify Basic Auth credentials from request
 */
function verifyBasicAuth(request: NextRequest): boolean {
  if (!API_USERNAME || !API_PASSWORD) return true; // Skip auth if not configured

  const authHeader = request.headers.get("authorization");
  if (!authHeader?.startsWith("Basic ")) return false;

  const base64Credentials = authHeader.slice(6);
  const credentials = Buffer.from(base64Credentials, "base64").toString(
    "utf-8",
  );
  const [username, password] = credentials.split(":");

  return username === API_USERNAME && password === API_PASSWORD;
}

/**
 * Return 401 response prompting for Basic Auth
 */
function unauthorizedResponse(): NextResponse {
  return new NextResponse("Authentication required", {
    status: 401,
    headers: {
      "WWW-Authenticate": `Basic realm="${AUTH_REALM}", charset="UTF-8"`,
    },
  });
}

function hasBody(method: string): boolean {
  return method !== "GET" && method !== "HEAD";
}

export async function proxy(request: NextRequest) {
  // Verify Basic Auth for all requests
  if (!verifyBasicAuth(request)) {
    return unauthorizedResponse();
  }

  const { pathname, search } = request.nextUrl;

  // Only proxy /api/* requests to backend
  if (!pathname.startsWith("/api")) {
    return NextResponse.next();
  }

  // Proxy API requests to backend
  const backendPath = pathname.replace(/^\/api/, "");
  const targetUrl = `${BACKEND_URL}${backendPath}${search}`;

  const headers = new Headers();
  // Forward the same auth to backend
  const credentials = Buffer.from(`${API_USERNAME}:${API_PASSWORD}`).toString(
    "base64",
  );
  headers.set("Authorization", `Basic ${credentials}`);

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
