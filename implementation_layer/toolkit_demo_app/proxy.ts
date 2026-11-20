import {
  SIGNED_IN_HEADER,
  USER_HEADER,
  namesItsUser,
  WIZARD_USER_HEADER,
  accessRefusal,
  handsOutStorageLink,
  isStateChanging,
  isWizardApiPath,
  needsApprovedUser,
  wizardRefusal,
  writesSharedData,
} from "@/lib/api-access";
import {
  MODEL_SETTINGS_HEADER,
  REASONING_EFFORT_HEADER,
  SERVER_MODEL_HEADER,
  isReasoningEffort,
  isServerModelId,
  encodeModelSettings,
  parseModelSettingsHeader,
  supportsModelSettings,
  supportsServerModel,
} from "@/lib/model-settings";
import {
  ADMIN_COOKIE_NAME,
  MODEL_TIER_HEADER,
  isModelStaff,
} from "@/lib/model-tier";
import { verifyAdminSessionValue } from "@/lib/admin/session";
import { isAnalyticsPath } from "@/lib/analytics-path";
import { backendTarget, isApiPath } from "@/lib/backend-target";
import { routedPath } from "@/lib/request-path";
import { clientIp } from "@/lib/client-ip";
import { checkRateLimit, ratelimit } from "@/lib/rate-limit";
import {
  type AccessState,
  getAccessState,
  updateSession,
  withSessionCookies,
} from "@/lib/supabase/proxy";
import { takeTrialRun } from "@/lib/trial";
import { recordWizardUse, wizardUseKind } from "@/lib/wizard-usage";
import { attachCsp, isPagePath, setCsp } from "@/lib/csp";
import {
  type BodyLimit,
  bodyLimitFor,
  declaresMoreThan,
  readBodyWithin,
} from "@/lib/upload-limits";
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

// A body over its route's limit (lib/upload-limits.ts). The pages read
// `detail` from the API's answers and `error` from the proxy's; both say it.
function tooLarge(limit: BodyLimit): NextResponse {
  return NextResponse.json(
    { error: limit.message, detail: limit.message },
    { status: 413 },
  );
}

// A page request gets a fresh nonce and its Content-Security-Policy, on the
// request, so the renderer stamps Next's own scripts with the nonce, and on the
// response (lib/csp.ts). Kept apart from the routing below.
export default async function proxy(request: NextRequest) {
  if (!isPagePath(request.nextUrl.pathname)) return route(request);
  const csp = attachCsp(request);
  return setCsp(await route(request), csp);
}

async function route(request: NextRequest): Promise<NextResponse> {
  // The rules below match the path the backend routes on (lib/request-path.ts);
  // the request is forwarded with the path as it was sent.
  const rawPath = request.nextUrl.pathname;
  const pathname = routedPath(rawPath);
  if (pathname === null)
    return NextResponse.json({ error: "Not found" }, { status: 404 });

  // Analytics requests go on to PostHog (lib/analytics-path.ts). Hand them on
  // without this site's cookies, and before the session is read or refreshed:
  // nothing here needs it, and a refresh would put new tokens in the request.
  if (isAnalyticsPath(pathname)) {
    const headers = new Headers(request.headers);
    headers.delete("cookie");
    return NextResponse.next({ request: { headers } });
  }

  // Read at most once per request, by the API gates. Reading it can refresh the
  // session, and every response below carries the new cookies.
  let access: AccessState | undefined;
  const accessState = async () => (access ??= await getAccessState(request));
  const reply = (response: NextResponse) =>
    withSessionCookies(response, access);

  // Proxy API requests to backend (except Next.js API routes)
  const isNextApiRoute =
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/api/admin") ||
    pathname === "/api/report-writer/run" || // owned by its route handler
    pathname === "/api/report-writer-v2/run" || // likewise
    pathname === "/api/source-normalizer/run" || // likewise
    pathname === "/api/knowledge-curator/run" || // likewise
    pathname === "/api/knowledge-synthesis/run" || // likewise
    pathname === "/api/helpdesk-chat" || // runs its model in Next.js
    pathname === "/api/ai-act-screening"; // likewise
  if (isApiPath(pathname) && !isNextApiRoute) {
    // Rate limit requests that change state (heavy processing, deletes). While
    // the configured Redis does not answer, the limiter refuses them (503).
    if (isStateChanging(request.method)) {
      const limited = await checkRateLimit(
        ratelimit,
        clientIp(request.headers),
        "Liian monta pyyntöä. Yritä hetken päästä uudelleen.",
        "[rate-limit]",
      );
      if (limited) {
        return NextResponse.json(
          { error: limited.error },
          { status: limited.status, headers: limited.headers },
        );
      }
    }

    // A body that declares more than its route takes is refused before any of
    // it is read, and before the gates below spend a trial run on it.
    const backendPath = pathname.slice("/api".length);
    const bodyLimit = bodyLimitFor(backendPath);
    if (
      hasBody(request.method) &&
      declaresMoreThan(request, bodyLimit.maxBytes)
    ) {
      await request.body?.cancel().catch(() => {});
      return tooLarge(bodyLimit);
    }

    // The first Solution Wizard has a gate of its own on top of the one below,
    // for every method: the per-user grant (lib/api-access.ts, wizardRefusal).
    const wizardApi = isWizardApiPath(pathname);
    if (wizardApi) {
      const refusal = wizardRefusal(await accessState());
      if (refusal) {
        console.warn(
          `[wizard-gate] ${refusal.status} ${request.method} ${pathname}`,
        );
        return reply(
          NextResponse.json(
            { error: refusal.error },
            { status: refusal.status },
          ),
        );
      }
    }

    // A signed storage link (a video's playback or thumbnail) is handed to a
    // signed-in user only; the API checks the header set further down.
    const storageLink = handsOutStorageLink(request.method, pathname);
    if (storageLink && !(await accessState()).loggedIn) {
      console.warn(
        `[api-gate] 401 ${request.method} ${pathname} loggedIn=false`,
      );
      return reply(
        NextResponse.json(
          { error: "Sign in to use this feature." },
          { status: 401 },
        ),
      );
    }

    // Require login + approval for every backend request that changes state,
    // not just POST: a DELETE clears data.
    // A user still waiting for approval runs on the daily trial allowance
    // (lib/trial.ts). A request that carries the user's own model key on a
    // supported route runs on their credential: it still needs a signed-in
    // account, approved, or pending with a confirmed e-mail address, but spends
    // no trial run. The header alone opens nothing. Neither covers a write to
    // data that every visitor shares: that needs the admin session.
    const ownModelKey =
      !!request.headers.get(MODEL_SETTINGS_HEADER) &&
      supportsModelSettings(pathname, request.method);
    if (needsApprovedUser(request.method)) {
      const state = await accessState();
      // Starting Aitta's idle models is no demo run, and neither is ending a
      // wizard session: they spend no trial run.
      const noTrialRun =
        pathname === "/api/model-settings/aitta/warm" ||
        (request.method === "DELETE" &&
          pathname.startsWith("/api/wizard/end/"));
      const sharedData = writesSharedData(request.method, pathname);
      const refusal = await accessRefusal(state, takeTrialRun, {
        ownModelKey,
        noTrialRun,
        sharedData,
        admin:
          sharedData &&
          verifyAdminSessionValue(
            request.cookies.get(ADMIN_COOKIE_NAME)?.value,
          ),
      });
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

    // A wizard session belongs to the user who started it. The API takes the
    // user from this header, which only the proxy sets: the headers sent to the
    // backend are built here, not copied from the browser's request.
    if (wizardApi) {
      const { userId } = await accessState();
      if (userId) headers.set(WIZARD_USER_HEADER, userId);
    }
    // A generated result (PDF, subtitles, tabular session) belongs to the user
    // whose run made it; the API serves it only to the same user. Set on every
    // run and on every result download (namesItsUser), never copied from the browser.
    // Other reads leave it out, so they do not read the session.
    if (namesItsUser(request.method, pathname)) {
      const { userId } = await accessState();
      if (userId) headers.set(USER_HEADER, userId);
    }

    // Only the proxy sets this header (`headers` starts empty), and only after
    // the check above found the user signed in.
    if (storageLink) headers.set(SIGNED_IN_HEADER, "1");

    // A server model the user picked. The API checks it against its own list.
    const serverModel = request.headers.get(SERVER_MODEL_HEADER);
    if (
      !modelSettings &&
      isServerModelId(serverModel) &&
      supportsServerModel(pathname, request.method)
    ) {
      headers.set(SERVER_MODEL_HEADER, serverModel);
    }
    // The reasoning effort picked with the model, on an own key as well. The
    // API applies it to GPT-6 models only; any other value is dropped here.
    const reasoningEffort = request.headers.get(REASONING_EFFORT_HEADER);
    if (
      isReasoningEffort(reasoningEffort) &&
      supportsServerModel(pathname, request.method)
    ) {
      headers.set(REASONING_EFFORT_HEADER, reasoningEffort);
    }
    // Tell the API whether this user may run the team-only models, from the
    // session (lib/model-tier.ts): on every run, which may name a model, and on
    // the two catalogues that list the models. The browser's own copy of this
    // header is never forwarded: `headers` starts empty.
    if (
      isStateChanging(request.method) ||
      backendPath === "/model-settings/server" ||
      backendPath === "/extract-vision/models"
    ) {
      const { email } = await accessState();
      if (isModelStaff(email, request.cookies.get(ADMIN_COOKIE_NAME)?.value))
        headers.set(MODEL_TIER_HEADER, "staff");
    }

    try {
      // Buffer the body to preserve binary integrity for large multipart
      // uploads (streaming truncates data in Bun/standalone), but only within
      // the route's limit: this copy stops at the first chunk past it.
      let body: ArrayBuffer | null = null;
      if (hasBody(request.method)) {
        body = await readBodyWithin(request, bodyLimit.maxBytes);
        if (body === null) return reply(tooLarge(bodyLimit));
        headers.set("content-length", body.byteLength.toString());
      }

      const response = await fetch(targetUrl, {
        method: request.method,
        headers,
        body,
        ...(modelSettings ? { redirect: "error" as const } : {}),
      });

      // A wizard session the API started, or a message it took, is counted
      // for the user, for /admin (lib/wizard-usage.ts). Not awaited: the count
      // must not hold the reply.
      const wizardUse = wizardApi
        ? wizardUseKind(request.method, pathname)
        : null;
      if (wizardUse && response.ok) {
        const { userId } = await accessState();
        if (userId) void recordWizardUse(userId, wizardUse);
      }

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
      // The reason names the backend's address; it goes to the log, not the page.
      const id = crypto.randomUUID().slice(0, 12);
      console.error(`[proxy] error id ${id}: backend request failed:`, error);
      return reply(
        NextResponse.json(
          {
            error: `The demo API did not answer (error id ${id}). Try again in a moment.`,
          },
          { status: 502 },
        ),
      );
    }
  }

  // Handle Supabase session for all non-API routes.
  const response = await updateSession(request);
  response.headers.set("x-current-path", rawPath);
  return response;
}
