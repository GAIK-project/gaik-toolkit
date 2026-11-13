// The path the access rules in proxy.ts are matched against.
//
// The backend (Starlette) routes on the request path after percent-decoding it
// once, so "/api/%65xtract" reaches the same route as "/api/extract". The rules
// match on that decoded form, so every spelling of a path meets the rule of the
// route it reaches. A path whose decoded form the rules cannot judge (it does not
// decode, or it holds control characters, a backslash, an empty segment or a
// dot segment) gets null and is refused.

const UNJUDGED = /[\u0000-\u001f\u007f\\]/;

export function routedPath(pathname: string): string | null {
  let decoded: string;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return null;
  }
  if (!decoded.startsWith("/") || UNJUDGED.test(decoded)) return null;
  const segments = decoded.slice(1).split("/");
  // A trailing slash leaves one empty last segment; any other empty one is "//".
  const inner = segments.at(-1) === "" ? segments.slice(0, -1) : segments;
  if (inner.some((s) => s === "" || s === "." || s === "..")) return null;
  return decoded;
}
