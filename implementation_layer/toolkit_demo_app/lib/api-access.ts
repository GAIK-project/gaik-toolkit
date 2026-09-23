// Which proxied backend requests need a signed-in, approved user.
//
// Anything that is not a read can change state or cost money: POST runs the
// heavy endpoints, and DELETE clears data (DELETE /video-search/clear empties
// the video_segments table). Gating only POST left the DELETE routes open to
// anonymous callers, so the gate keys on the method being a read, not on POST.

const READ_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export function isStateChanging(method: string): boolean {
  return !READ_METHODS.has(method.toUpperCase());
}

export function needsApprovedUser(method: string, pathname: string): boolean {
  // The wizard API has its own gate, including the team-key path.
  return isStateChanging(method) && !pathname.startsWith("/api/wizard");
}
