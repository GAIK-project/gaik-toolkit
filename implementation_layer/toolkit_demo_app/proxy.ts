import {
  accessRefusal,
  isStateChanging,
  needsApprovedUser,
} from "@/lib/api-access";
import {
  MODEL_SETTINGS_HEADER,
  SERVER_MODEL_HEADER,
  isServerModelId,
  encodeModelSettings,
  parseModelSettingsHeader,
  supportsModelSettings,
} from "@/lib/model-settings";
import {
  ADMIN_COOKIE_NAME,
  MODEL_TIER_HEADER,
  isModelStaff,
} from "@/lib/model-tier";
import { backendTarget, isApiPath } from "@/lib/backend-target";
import { routedPath } from "@/lib/request-path";
import { clientIp } from "@/lib/client-ip";
import { ratelimit } from "@/lib/rate-limit";
import {
  type AccessState,
  getAccessState,
  updateSession,
  withSessionCookies,
} from "@/lib/supabase/proxy";
import { takeTrialRun } from "@/lib/trial";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|logos/|data/|downloads/).*)",
  ],
};

function hasBody(method: string): boolean {
  return method !== "GET" && method !== "HEAD";
}

export default async function proxy(request: NextRequest) {
  // The rules below match the path the backend routes on (lib/request-path.ts);
  // the request is forwarded with the path as it was sent.
  const rawPath = request.nextUrl.pathname;
  const pathname = routedPath(rawPath);
  if (pathname === null)
    return NextResponse.json({ error: "Not found" }, { status: 404 });

  // Read once per request and shared by the wizard and API gates. Reading it can
  // refresh the session, and every response below carries the new cookies.
  let access: AccessState | undefined;
  const accessState = async () => (access ??= await getAccessState(request));
  const reply = (response: NextResponse) =>
    withSessionCookies(response, access);

  // Old Solution Wizard API gate. The wizard runs as Wizard V2 and the demo API no
  // longer serves /wizard, so nothing behind this path answers; the gate stays
  // until it is removed with the wizard_access grant. The /solution-wizard page is
  // only a notice that links to Wizard V2 and is open to everyone. Two ways in:
  //   1. Team shortcut: the `wizard_access` cookie equal to WIZARD_ACCESS_SECRET.
  //   2. Registered beta testers: a logged-in user whose access_requests row
  //      has wizard_access = true (granted by an admin in /admin).
  // Dev: BYPASS_AUTH opens it. Default-deny otherwise.
  if (pathname.startsWith("/api/wizard")) {
    const secret = process.env.WIZARD_ACCESS_SECRET;
    const teamAllowed =
      !!secret && request.cookies.get("wizard_access")?.value === secret;
    if (!teamAllowed && !(await accessState()).wizardAccess) {
      return reply(
        NextResponse.json(
          { error: "Solution Wizard is not available yet." },
          { status: 403 },
        ),
      );
    }
  }

  // Proxy API requests to backend (except Next.js API routes)
  const isNextApiRoute =
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/api/admin") ||
    pathname === "/api/report-writer/run" || // owned by its route handler
    pathname === "/api/report-writer-v2/run" || // likewise
    pathname === "/api/source-normalizer/run" || // likewise
    pathname === "/api/knowledge-curator/run" || // likewise
    pathname === "/api/knowledge-synthesis/run" || // likewise
    pathname === "/api/helpdesk-chat"; // runs its model in Next.js
  if (isApiPath(pathname) && !isNextApiRoute) {
    // Rate limit requests that change state (heavy processing, deletes)
    if (ratelimit && isStateChanging(request.method)) {
      try {
        const ip = clientIp(request.headers);

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

    // Require login + approval for every backend request that changes state,
    // not just POST: DELETE /video-search/clear empties a table.
    // A user still waiting for approval runs on the daily trial allowance
    // (lib/trial.ts). A request that carries the user's own model key on a
    // supported route runs on their credential: it still needs a signed-in
    // account, approved or pending, but spends no trial run.
    const ownModelKey =
      !!request.headers.get(MODEL_SETTINGS_HEADER) &&
      supportsModelSettings(pathname, request.method);
    if (needsApprovedUser(request.method, pathname)) {
      const state = await accessState();
      const refusal = await accessRefusal(state, takeTrialRun, ownModelKey);
      if (refusal) {
        // Why a run was refused, without who: the page shows the same text.
        console.warn(
          `[api-gate] ${refusal.status} ${request.method} ${pathname} loggedIn=${state.loggedIn} approved=${state.approved} pending=${state.pending}`,
        );
        return reply(
          NextResponse.json(
            { error: refusal.error },
            { status: refusal.status },
          ),
        );
      }
    }

    const backendPath = pathname.slice("/api".length);
    // Null when the URL would not be on the backend's own origin.
    const targetUrl = backendTarget(
      BACKEND_URL,
      rawPath,
      request.nextUrl.search,
    );
    if (!targetUrl) {
      return reply(NextResponse.json({ error: "Not found" }, { status: 404 }));
    }

    const headers = new Headers();
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);
    const modelSettings = request.headers.get(MODEL_SETTINGS_HEADER);
    if (modelSettings) {
      if (!supportsModelSettings(pathname, request.method)) {
        return reply(
          NextResponse.json(
            { error: "This demo uses server model settings." },
            { status: 400 },
          ),
        );
      }
      try {
        headers.set(
          MODEL_SETTINGS_HEADER,
          encodeModelSettings(parseModelSettingsHeader(modelSettings)),
        );
      } catch {
        return reply(
          NextResponse.json(
            { error: "Invalid model settings." },
            { status: 400 },
          ),
        );
      }
    }

    // A server model the user picked. The API checks it against its own list.
    const serverModel = request.headers.get(SERVER_MODEL_HEADER);
    if (
      !modelSettings &&
      isServerModelId(serverModel) &&
      supportsModelSettings(pathname, request.method)
    ) {
      headers.set(SERVER_MODEL_HEADER, serverModel);
    }
    // Tell the API whether this user may run the team-only models.
    if (
      headers.has(SERVER_MODEL_HEADER) ||
      backendPath === "/model-settings/server"
    ) {
      const { email } = await accessState();
      if (isModelStaff(email, request.cookies.get(ADMIN_COOKIE_NAME)?.value))
        headers.set(MODEL_TIER_HEADER, "staff");
    }

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
        ...(modelSettings ? { redirect: "error" as const } : {}),
      });

      // For SSE streaming responses, pass through directly
      if (response.headers.get("content-type")?.includes("text/event-stream")) {
        return reply(
          new NextResponse(response.body, {
            status: response.status,
            statusText: response.statusText,
            headers: {
              "Content-Type": "text/event-stream",
              "Cache-Control": modelSettings
                ? "no-store, no-transform"
                : "no-cache, no-transform",
              "X-Accel-Buffering": "no",
            },
          }),
        );
      }

      return reply(
        new NextResponse(response.body, {
          status: response.status,
          statusText: response.statusText,
          headers: new Headers(response.headers),
        }),
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "Proxy error";
      return reply(NextResponse.json({ error: message }, { status: 502 }));
    }
  }

  // Handle Supabase session for all non-API routes. A refresh in the wizard
  // gate is handed on, so updateSession does not spend the old token again.
  for (const { name, value } of access?.cookies ?? [])
    request.cookies.set(name, value);
  const response = reply(await updateSession(request));
  response.headers.set("x-current-path", rawPath);
  return response;
}
