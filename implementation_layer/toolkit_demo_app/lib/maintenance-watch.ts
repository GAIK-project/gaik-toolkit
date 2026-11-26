// The browser's side of maintenance mode (lib/maintenance.ts): once the mode is
// on, an open page's next API call gets 503 with this header, and the page
// reloads into the maintenance page instead of showing an error. Kept apart
// from lib/maintenance.ts so the client bundle does not pull in next/server.

/** Header on every refusal the maintenance gate sends. */
export const MAINTENANCE_HEADER = "x-demo-maintenance";

/** True for a response the maintenance gate sent. */
export function isMaintenanceResponse(response: {
  status: number;
  headers: Headers;
}): boolean {
  return (
    response.status === 503 && response.headers.get(MAINTENANCE_HEADER) === "on"
  );
}

type FetchHost = { fetch: typeof fetch };
type Watched = typeof fetch & { [WATCHED]?: typeof fetch };

const WATCHED = Symbol.for("gaik.demo.maintenanceWatch");

/**
 * Wraps `host.fetch` so that a maintenance refusal calls `onMaintenance`, once.
 * The response still goes back to the caller unchanged. Installing twice (a
 * remount) wraps only once. Returns a function that puts the original back.
 */
export function watchForMaintenance(
  host: FetchHost,
  onMaintenance: () => void,
): () => void {
  const original = host.fetch as Watched;
  if (original[WATCHED]) return () => {};
  let fired = false;
  const wrapped = (async (...args: Parameters<typeof fetch>) => {
    const response = await original(...args);
    if (!fired && isMaintenanceResponse(response)) {
      fired = true;
      onMaintenance();
    }
    return response;
  }) as Watched;
  wrapped[WATCHED] = original;
  host.fetch = wrapped;
  return () => {
    if (host.fetch === wrapped) host.fetch = original;
  };
}
