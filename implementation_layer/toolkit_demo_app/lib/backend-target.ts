// Where the proxy sends an API request.
//
// The proxy forwards "/api/<path>" to "<BACKEND_URL>/<path>". The path comes
// from the request, so the target is checked before it is fetched: it must
// stay on the backend's own origin.

/** True for "/api" and the paths below it; false for "/apix" or "/api.txt". */
export function isApiPath(pathname: string): boolean {
  return pathname === "/api" || pathname.startsWith("/api/");
}

/**
 * The backend URL for an API path, or null when the path is not an API path
 * or the URL would leave the backend's origin.
 */
export function backendTarget(
  backendUrl: string,
  pathname: string,
  search = "",
): string | null {
  if (!isApiPath(pathname)) return null;
  let base: URL;
  let target: URL;
  try {
    base = new URL(backendUrl);
    target = new URL(
      `${backendUrl.replace(/\/+$/, "")}${pathname.slice("/api".length)}${search}`,
    );
  } catch {
    return null;
  }
  if (target.origin !== base.origin || target.username || target.password)
    return null;
  return target.toString();
}
