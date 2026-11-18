import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";
import { DEV_AUTH, DEV_COOKIE } from "@/lib/auth";
import { verifyDevSession } from "@/lib/dev-session";
import { ACCESS_TOKEN_HEADER, proxyAuthEnabled, verifyAccessToken } from "@/lib/proxy-auth";
import { TRACE_HEADER } from "@/lib/trace-header";
import { isPublicPage } from "@/lib/public-pages";
import { isCrossSiteWrite } from "@/lib/same-origin";
import { attachCsp, setCsp } from "@/lib/csp";

// The proxy runs before the route, in a call of its own, so the traceId
// reaches the route as a header, not through the AsyncLocalStorage context
// that route handlers get via withLogging (lib/with-logging.ts).
function withTraceId(request: NextRequest, response: NextResponse): NextResponse {
  const traceId = request.headers.get(TRACE_HEADER) ?? crypto.randomUUID();
  response.headers.set(TRACE_HEADER, traceId);
  return response;
}

function nextWithTraceId(request: NextRequest): NextResponse {
  const traceId = request.headers.get(TRACE_HEADER) ?? crypto.randomUUID();
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set(TRACE_HEADER, traceId);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set(TRACE_HEADER, traceId);
  return response;
}

export async function proxy(request: NextRequest) {
  // A fresh nonce and the Content-Security-Policy go on the request, so the
  // renderer stamps Next's own scripts with the nonce, and on every response
  // below (lib/csp).
  const csp = attachCsp(request);
  return setCsp(await route(request), csp);
}

async function route(request: NextRequest): Promise<NextResponse> {
  // A write to the API from another site is refused before anything else
  // (lib/same-origin). The upload routes the matcher leaves out check it
  // themselves.
  if (request.nextUrl.pathname.startsWith("/api/") && isCrossSiteWrite(request)) {
    return withTraceId(request, new NextResponse("Cross-site request refused", { status: 403 }));
  }

  // Proxy sign-in (lib/proxy-auth): oauth2-proxy in front has signed the user
  // in; the forwarded token is checked here, not trusted. Without a valid one
  // a page goes to the proxy's sign-in and an API call gets 401. The login page
  // has nothing to do in this mode and sends the browser on as well.
  if (proxyAuthEnabled()) {
    const path = request.nextUrl.pathname;
    const user = await verifyAccessToken(request.headers.get(ACCESS_TOKEN_HEADER));
    if (user) {
      if (path === "/login") {
        const url = request.nextUrl.clone();
        url.pathname = "/";
        url.search = "";
        return withTraceId(request, NextResponse.redirect(url));
      }
      return nextWithTraceId(request);
    }
    if (isPublicPage(path) && path !== "/login") return nextWithTraceId(request);
    if (path.startsWith("/api/")) {
      return withTraceId(request, new NextResponse("Sign-in required", { status: 401 }));
    }
    const url = request.nextUrl.clone();
    url.pathname = "/oauth2/start";
    // Back to the page asked for, its query included.
    const back = path === "/login" ? "/" : `${path}${request.nextUrl.search}`;
    url.search = `?rd=${encodeURIComponent(back)}`;
    return withTraceId(request, NextResponse.redirect(url));
  }

  // Dev mode: signed cookie check (lib/dev-session), no Supabase.
  if (DEV_AUTH) {
    const email = await verifyDevSession(request.cookies.get(DEV_COOKIE)?.value);
    const hasSession = email !== null;
    const path = request.nextUrl.pathname;
    const isPublic =
      isPublicPage(path) || path.startsWith("/api/dev/");
    if (!hasSession && !isPublic) {
      const url = request.nextUrl.clone();
      url.pathname = "/login";
      return withTraceId(request, NextResponse.redirect(url));
    }
    return nextWithTraceId(request);
  }

  // Production path: Supabase session refresh + route protection.
  // Only sets the *response* traceId header here, not a request header into
  // updateSession — that function has an explicit "don't add code between
  // getUser and returning the response" warning for cookie-refresh
  // correctness, and this path is dormant without NEXT_PUBLIC_SUPABASE_URL
  // (dev/demo always takes the DEV_AUTH branch above). Route handlers still
  // get a valid traceId either way — withLogging generates one when the
  // request header is missing. The nonce headers need no such step: they were
  // put on the request itself above, and updateSession's `NextResponse.next({
  // request })` forwards them.
  return withTraceId(request, await updateSession(request));
}

export const config = {
  // No `runtime` here: a proxy always runs on Node.js (Next.js 16), and this
  // one has to. WIZARD_AUTH_MODE and the WIZARD_OIDC_* settings are read the
  // same way, at run time. The dev session is checked against WIZARD_DEV_USERS and signed
  // with NEXT_SERVER_ACTIONS_ENCRYPTION_KEY, both set when the pod starts; on
  // the Edge runtime only what was there at build time is seen, so on a
  // deployed stack every signed cookie was rejected and nobody could sign in.
  //
  // The file uploads are left out. On the Node.js runtime the proxy hands
  // the route a copy of the request, and a body that arrives in parts (any
  // upload through the Rahti router) reached the route cut short: "Failed to
  // parse body as FormData", one upload in three. Those routes check the
  // signed-in owner themselves (requireOwnedSession), as every API route does.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|api/sessions/[^/]+/poc/input$|api/sessions/[^/]+/cases/[^/]+/inputs$|(?!api/).*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
