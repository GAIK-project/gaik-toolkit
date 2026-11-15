/**
 * The client address for rate limits and trial counts.
 *
 * The Rahti router appends the address it received the connection from to
 * x-forwarded-for, so the last entry is the one the router vouches for.
 * Earlier entries are whatever the client sent and change at will.
 */
export function clientIp(headers: Headers): string {
  return (
    headers.get("x-forwarded-for")?.split(",").at(-1)?.trim() ||
    headers.get("x-real-ip")?.trim() ||
    "anonymous"
  );
}
