// Cross-site request guard for state-changing API calls.
//
// Route handlers, unlike Server Actions, get no Origin check from Next, and a
// cross-site form or fetch with a simple content type still carries the
// session cookie (SameSite=Lax lets top-level POSTs from the same site through,
// and other apps on the same parent domain may count as the same site). A
// browser always sends Origin on such a request, so a write whose Origin is not
// this host is refused. Calls without Origin and Sec-Fetch-Site (scripts, test
// clients) are not browser requests and are left to the session check.

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function requestHost(headers: Headers): string | null {
  const forwarded = headers.get("x-forwarded-host")?.split(",")[0]?.trim();
  return forwarded || headers.get("host");
}

const DEFAULT_PORTS: Record<string, string> = { "http:": "80", "https:": "443" };

// The host as the browser names it: a proxy may add the scheme's default port
// (host:443) that the Origin header leaves out.
function sameHost(origin: URL, host: string): boolean {
  const suffix = `:${DEFAULT_PORTS[origin.protocol] ?? ""}`;
  const bare = (h: string) => {
    const lower = h.toLowerCase();
    return lower.endsWith(suffix) ? lower.slice(0, -suffix.length) : lower;
  };
  return bare(origin.host) === bare(host);
}

export function isCrossSiteWrite(req: { method: string; headers: Headers }): boolean {
  if (SAFE_METHODS.has(req.method.toUpperCase())) return false;
  const origin = req.headers.get("origin");
  if (origin) {
    const host = requestHost(req.headers);
    try {
      return !host || !sameHost(new URL(origin), host);
    } catch {
      return true; // "null" (sandboxed frames, file:) and other non-URLs
    }
  }
  const site = req.headers.get("sec-fetch-site");
  if (site) return site !== "same-origin" && site !== "none";
  return false;
}
